from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from io import StringIO

from reading.models import ActivityTurn, CachedReply, ReadingSession


SRC = "marx"


STATIC_OK = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def fake_stream(pieces=("Hello ", "world.")):
    calls = []

    def _stream(model, system, user, options=None):
        calls.append((model, system, user))
        yield from pieces

    _stream.calls = calls
    return _stream


@override_settings(STORAGES=STATIC_OK)
class CacheTests(TestCase):
    def setUp(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": "marx"}))
        self.session = ReadingSession.objects.get()

    def generate(self, activity="pre_reading", query="", client=None, stream=None):
        client = client or self.client
        url = reverse("reading:generate", kwargs={"pk": self.session.pk, "activity_id": activity})
        with mock.patch("reading.views.stream_reply", stream or fake_stream()):
            response = client.post(url + query)
            return response, b"".join(response.streaming_content if response.streaming else [response.content]).decode()

    def test_first_generate_calls_llm_and_stores_reply(self):
        stream = fake_stream()
        _, body = self.generate(stream=stream)
        self.assertEqual(body, "Hello world.")
        self.assertEqual(len(stream.calls), 1)
        self.assertEqual(CachedReply.objects.get().content, "Hello world.")

    def test_second_reader_gets_cached_reply_without_llm_call(self):
        self.generate()
        # a different browser opens the same library text
        other = self.client_class()
        other.get(reverse("reading:open", kwargs={"source_ref": "marx"}))
        other_session = ReadingSession.objects.exclude(pk=self.session.pk).get()
        url = reverse("reading:generate", kwargs={"pk": other_session.pk, "activity_id": "pre_reading"})
        stream = fake_stream(("DIFFERENT",))
        with mock.patch("reading.views.stream_reply", stream):
            response = other.post(url)
            body = b"".join(response.streaming_content if response.streaming else [response.content]).decode()
        self.assertEqual(body, "Hello world.")
        self.assertEqual(stream.calls, [])
        # the reader's own history still records the turn
        turn = ActivityTurn.objects.get(session=other_session)
        self.assertEqual((turn.turn, turn.content), ("user", "Hello world."))
        self.assertEqual(CachedReply.objects.get().hits, 1)

    def test_second_generate_by_same_reader_is_refused(self):
        self.generate()
        stream = fake_stream(("Fresh take.",))
        response, body = self.generate(stream=stream)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(stream.calls, [])
        self.assertEqual(ActivityTurn.objects.filter(session=self.session).count(), 1)
        self.assertEqual(CachedReply.objects.get().content, "Hello world.")

    def test_cached_hit_also_blocks_a_second_generate(self):
        self.generate()
        other = self.client_class()
        other.get(reverse("reading:open", kwargs={"source_ref": SRC}))
        sess = ReadingSession.objects.exclude(pk=self.session.pk).get()
        url = reverse("reading:generate", kwargs={"pk": sess.pk, "activity_id": "pre_reading"})
        with mock.patch("reading.views.stream_reply", fake_stream(("X",))):
            self.assertEqual(other.post(url).status_code, 200)   # served from cache
            self.assertEqual(other.post(url).status_code, 409)   # now blocked
        self.assertEqual(ActivityTurn.objects.filter(session=sess).count(), 1)

    def test_generate_allowed_again_after_reset_and_served_from_cache(self):
        self.generate()
        self.client.post(reverse("reading:reset", kwargs={"pk": self.session.pk}), follow=True)
        sess = ReadingSession.objects.get()  # reset reopens a fresh session
        url = reverse("reading:generate", kwargs={"pk": sess.pk, "activity_id": "pre_reading"})
        stream = fake_stream(("X",))
        with mock.patch("reading.views.stream_reply", stream):
            body = b"".join([self.client.post(url).content]).decode()
        self.assertEqual(body, "Hello world.")
        self.assertEqual(stream.calls, [])

    def test_different_level_does_not_share_an_entry(self):
        self.generate()
        other = self.client_class()
        other.get(reverse("reading:open", kwargs={"source_ref": "marx"}))
        other_session = ReadingSession.objects.exclude(pk=self.session.pk).get()
        ReadingSession.objects.filter(pk=other_session.pk).update(level_id="introductory")
        url = reverse("reading:generate", kwargs={"pk": other_session.pk, "activity_id": "pre_reading"})
        stream = fake_stream(("B",))
        with mock.patch("reading.views.stream_reply", stream):
            body = b"".join(other.post(url).streaming_content).decode()
        self.assertEqual(body, "B")
        self.assertEqual(CachedReply.objects.count(), 2)

    def test_changed_prompt_misses_the_cache(self):
        self.generate()
        with mock.patch("reading.views.load_prompts") as lp:
            from reading.logic.prompts import load_prompts
            prompts = load_prompts()
            prompts = {**prompts, "shared": {**prompts["shared"], "system": prompts["shared"]["system"] + "\nEXTRA RULE"}}
            lp.return_value = prompts
            stream = fake_stream(("New prompt output",))
            other = self.client_class()
            other.get(reverse("reading:open", kwargs={"source_ref": SRC}))
            sess = ReadingSession.objects.exclude(pk=self.session.pk).get()
            url = reverse("reading:generate", kwargs={"pk": sess.pk, "activity_id": "pre_reading"})
            with mock.patch("reading.views.stream_reply", stream):
                body = b"".join(other.post(url).streaming_content).decode()
        self.assertEqual(body, "New prompt output")

    def test_uploaded_texts_are_never_cached(self):
        other = self.client_class()
        other.post(reverse("reading:upload"), {
            "file": SimpleUploadedFile("mine.txt", ("Das ist mein eigener deutscher Text. " * 10).encode()),
            "language": "de"})
        sess = ReadingSession.objects.get(uploaded=True)
        url = reverse("reading:generate", kwargs={"pk": sess.pk, "activity_id": "pre_reading"})
        with mock.patch("reading.views.stream_reply", fake_stream()):
            b"".join(other.post(url).streaming_content)
        self.assertEqual(CachedReply.objects.count(), 0)

    def test_llm_error_is_not_cached(self):
        from reading.logic.llm import LLMError

        def boom(*a, **k):
            raise LLMError("down")
            yield  # pragma: no cover

        _, body = self.generate(stream=boom)
        self.assertIn("Something went wrong", body)
        self.assertEqual(CachedReply.objects.count(), 0)

    def test_empty_reply_is_not_cached(self):
        self.generate(stream=fake_stream(("  \n",)))
        self.assertEqual(CachedReply.objects.count(), 0)

    def test_feedback_turns_are_never_cached(self):
        self.generate(activity="summative_comprehension")
        url = reverse("reading:submit", kwargs={"pk": self.session.pk, "activity_id": "summative_comprehension"})
        with mock.patch("reading.views.stream_reply", fake_stream(("Good.",))):
            b"".join(self.client.post(url, {"draft": "my answers"}).streaming_content)
        self.assertEqual(CachedReply.objects.count(), 1)  # only the opening turn

    def test_concurrent_duplicate_store_is_harmless(self):
        self.generate()
        row = CachedReply.objects.get()
        # a second writer racing with the same key must not raise
        CachedReply.store(key=row.key, activity_id="x", level_id="y", reply_language="",
                          model="m", source_ref="s", content="other")
        self.assertEqual(CachedReply.objects.count(), 1)
        self.assertEqual(CachedReply.objects.get().content, "Hello world.")


class ClearCommandTests(TestCase):
    def setUp(self):
        for i, act in enumerate(("pre_reading", "style")):
            CachedReply.objects.create(key=str(i) * 64, activity_id=act, level_id="intermediate",
                                       reply_language="", model="m", source_ref="lib:de-01", content="x")

    def test_clear_all(self):
        call_command("clear_reply_cache", "--all", stdout=StringIO())
        self.assertEqual(CachedReply.objects.count(), 0)

    def test_clear_by_activity(self):
        call_command("clear_reply_cache", "--activity", "style", stdout=StringIO())
        self.assertEqual(list(CachedReply.objects.values_list("activity_id", flat=True)), ["pre_reading"])

    def test_requires_a_selector(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("clear_reply_cache", stdout=StringIO())


@override_settings(STORAGES=STATIC_OK)
class GenerateButtonTests(TestCase):
    def setUp(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": SRC}))
        self.session = ReadingSession.objects.get()

    def page(self, activity):
        return self.client.get(reverse("reading:activity", kwargs={"pk": self.session.pk, "activity_id": activity}))

    def generate(self, activity):
        url = reverse("reading:generate", kwargs={"pk": self.session.pk, "activity_id": activity})
        with mock.patch("reading.views.stream_reply", fake_stream(("A result.",))):
            b"".join(self.client.post(url).streaming_content)

    def test_button_shown_before_and_hidden_after_for_plain_activity(self):
        self.assertContains(self.page("pre_reading"), 'id="generate-btn"')
        self.generate("pre_reading")
        page = self.page("pre_reading")
        self.assertNotContains(page, 'id="generate-btn"')
        self.assertNotContains(page, "Regenerate")
        self.assertContains(page, "A result.")

    def test_question_set_button_hidden_after_generation_but_answer_box_stays(self):
        self.assertContains(self.page("summative_comprehension"), "Generate questions")
        self.generate("summative_comprehension")
        page = self.page("summative_comprehension")
        self.assertNotContains(page, 'id="generate-btn"')
        self.assertNotContains(page, "New questions")
        self.assertContains(page, 'id="draft-form"')


@override_settings(STORAGES=STATIC_OK)
class KeepPositionScriptTests(TestCase):
    def test_activity_page_loads_the_keep_position_script_before_generate_js(self):
        self.client.get(reverse("reading:open", kwargs={"source_ref": SRC}))
        session = ReadingSession.objects.get()
        page = self.client.get(reverse("reading:activity", kwargs={"pk": session.pk, "activity_id": "pre_reading"}))
        html = page.content.decode()
        self.assertIn("keep-position.js", html)
        self.assertLess(html.index("keep-position.js"), html.index("generate.js"))

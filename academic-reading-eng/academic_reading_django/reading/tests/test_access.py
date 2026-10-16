from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase
from django.urls import reverse

from accounts.models import GroupAccess
from reading.access import library_for, texts_visible_to
from reading.logic.settings import load_config
from reading.models import LibraryText, ReadingSession
from reading.tests.helpers import new_user, signed_in_client


def make_text(ref, language="German", groups=(), active=True):
    text = LibraryText.objects.create(
        source_ref=ref, title=f"Title {ref}", language=language, body=f"Body of {ref}. " * 20, active=active
    )
    text.groups.set(groups)
    return text


class VisibilityRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.arabic = Group.objects.create(name="Arabic")
        cls.french = Group.objects.create(name="French")
        cls.technical = Group.objects.create(name="Technical")
        GroupAccess.objects.create(group=cls.technical, sees_all_texts=True)
        make_text("open-1")                                    # ungrouped
        make_text("ar-1", language="Arabic", groups=[cls.arabic])
        make_text("fr-1", language="French", groups=[cls.french])
        make_text("both-1", language="Arabic", groups=[cls.arabic, cls.french])
        make_text("hidden-1", active=False)                    # ungrouped but inactive

    def refs(self, user):
        return set(texts_visible_to(user).values_list("source_ref", flat=True))

    def test_anonymous_sees_nothing(self):
        self.assertEqual(self.refs(AnonymousUser()), set())
        self.assertEqual(library_for(AnonymousUser(), load_config()), ([], []))

    def test_signed_in_without_groups_sees_only_ungrouped(self):
        self.assertEqual(self.refs(new_user()), {"open-1"})

    def test_group_member_sees_own_groups_texts_plus_ungrouped(self):
        user = new_user()
        user.groups.add(self.arabic)
        self.assertEqual(self.refs(user), {"open-1", "ar-1", "both-1"})

    def test_several_groups_are_a_union(self):
        user = new_user()
        user.groups.add(self.arabic, self.french)
        self.assertEqual(self.refs(user), {"open-1", "ar-1", "fr-1", "both-1"})

    def test_text_in_two_groups_is_listed_once(self):
        user = new_user()
        user.groups.add(self.arabic, self.french)
        self.assertEqual(texts_visible_to(user).filter(source_ref="both-1").count(), 1)

    def test_sees_all_group_sees_every_active_text(self):
        user = new_user()
        user.groups.add(self.technical)
        self.assertEqual(self.refs(user), {"open-1", "ar-1", "fr-1", "both-1"})

    def test_staff_and_superuser_see_every_active_text(self):
        everything = {"open-1", "ar-1", "fr-1", "both-1"}
        self.assertEqual(self.refs(new_user(is_staff=True)), everything)
        self.assertEqual(self.refs(new_user(is_superuser=True)), everything)

    def test_inactive_text_is_hidden_from_everyone(self):
        user = new_user(is_superuser=True)
        self.assertNotIn("hidden-1", self.refs(user))


class LanguageOnSaveTests(TestCase):
    def test_stated_language_is_normalised(self):
        text = make_text("a", language="ar")
        self.assertEqual((text.lang, text.language_name), ("ar", "Arabic"))

    def test_blank_language_is_detected_from_the_body(self):
        text = LibraryText.objects.create(
            source_ref="g", title="G", body="Das ist ein deutscher Text über die Geschichte der Stadt. " * 8
        )
        self.assertEqual(text.lang, "de")
        self.assertEqual(text.language_name, "German")


class ViewEnforcementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.arabic = Group.objects.create(name="Arabic")
        make_text("open-1")
        make_text("ar-1", language="Arabic", groups=[cls.arabic])

    def setUp(self):
        self.browser = signed_in_client()
        self.user = self.browser.user

    def open(self, ref):
        return self.browser.get(reverse("reading:open", kwargs={"source_ref": ref}))

    def home_refs(self):
        return {t.id for t in self.browser.get(reverse("reading:home")).context["texts"]}

    def test_hidden_text_is_404_even_by_guessed_url(self):
        self.assertEqual(self.open("ar-1").status_code, 404)
        self.assertEqual(ReadingSession.objects.count(), 0)

    def test_hidden_text_not_in_the_home_list(self):
        self.assertEqual(self.home_refs(), {"open-1"})

    def test_joining_a_group_takes_effect_on_the_next_request(self):
        self.assertEqual(self.open("ar-1").status_code, 404)
        self.user.groups.add(self.arabic)
        self.assertEqual(self.open("ar-1").status_code, 302)
        self.assertEqual(self.home_refs(), {"open-1", "ar-1"})

    def test_leaving_a_group_blocks_the_existing_session_and_hides_it_from_history(self):
        self.user.groups.add(self.arabic)
        self.open("ar-1")
        session = ReadingSession.objects.get()
        self.assertEqual(self.browser.get(reverse("reading:read", kwargs={"pk": session.pk})).status_code, 302)
        self.user.groups.remove(self.arabic)
        activity = {"pk": session.pk, "activity_id": "pre_reading"}
        for name in ("reading:read", "reading:activity", "reading:generate", "reading:submit"):
            kwargs = {"pk": session.pk} if name == "reading:read" else activity
            response = self.browser.post(reverse(name, kwargs=kwargs)) if name in ("reading:generate", "reading:submit") \
                else self.browser.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 404, name)
        self.assertNotContains(self.browser.get(reverse("reading:history")), session.title)
        self.assertEqual(self.browser.get(reverse("reading:home")).context["history"], [])

    def test_deactivating_a_text_blocks_it_for_everyone(self):
        LibraryText.objects.filter(source_ref="open-1").update(active=False)
        self.assertEqual(self.open("open-1").status_code, 404)

    def test_uploads_stay_available_whatever_the_groups(self):
        session = ReadingSession.objects.create(
            user=self.user, session_key="k", source_ref="upload:abc", title="Mine", language_code="de",
            language_name="German", level_id="intermediate", body="x", uploaded=True
        )
        self.assertEqual(self.browser.get(reverse("reading:read", kwargs={"pk": session.pk})).status_code, 302)

    def test_files_mode_treats_every_text_as_ungrouped(self):
        from django.test import override_settings

        with override_settings(LIBRARY_SOURCE="files"):
            self.assertEqual(self.open("marx").status_code, 302)

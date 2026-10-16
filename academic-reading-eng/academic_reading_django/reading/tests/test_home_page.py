from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.models import GroupAccess
from reading.tests.helpers import new_user


class HomePageTests(TestCase):
    def home(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("reading:home"))

    # -- upload info icon -------------------------------------------------- #
    def test_upload_info_icon_is_shown_before_any_upload(self):
        page = self.home(new_user())
        self.assertContains(page, 'class="info-tip"')
        self.assertContains(page, "What kind of file can I upload?")
        for needle in (".txt", ".md", "UTF-8", "private to you"):
            self.assertContains(page, needle)
        # it sits before the upload form
        html = page.content.decode()
        self.assertLess(html.index('class="info-tip"'), html.index('class="upload-form"'))

    # -- library search is only for people who see every text -------------- #
    def test_search_hidden_for_an_ordinary_reader(self):
        page = self.home(new_user())
        self.assertNotContains(page, 'id="library-search"')
        self.assertNotContains(page, 'id="library-language"')
        self.assertFalse(page.context["can_search"])

    def test_search_hidden_for_a_member_of_a_limited_group(self):
        user = new_user()
        user.groups.add(Group.objects.create(name="Arabic"))
        self.assertNotContains(self.home(user), 'id="library-search"')

    def test_search_shown_to_staff_and_superusers(self):
        for flags in ({"is_staff": True}, {"is_superuser": True}):
            page = self.home(new_user(**flags))
            self.assertContains(page, 'id="library-search"')
            self.assertContains(page, 'id="library-language"')
            self.assertTrue(page.context["can_search"])

    def test_search_shown_to_a_sees_every_text_group(self):
        user = new_user()
        technical = Group.objects.create(name="Technical")
        GroupAccess.objects.create(group=technical, sees_all_texts=True)
        user.groups.add(technical)
        self.assertContains(self.home(user), 'id="library-search"')

    def test_group_without_the_tick_does_not_unlock_search(self):
        user = new_user()
        group = Group.objects.create(name="Technical")
        GroupAccess.objects.create(group=group, sees_all_texts=False)
        user.groups.add(group)
        self.assertNotContains(self.home(user), 'id="library-search"')

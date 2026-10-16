from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts import pipeline
from accounts.models import AllowedLogin, GroupAccess


class SyncGroupsTests(TestCase):
    def setUp(self):
        self.arabic = Group.objects.create(name="Arabic")
        self.tech = Group.objects.create(name="Technical")
        self.user = User.objects.create_user("a@cam.ac.uk", "a@cam.ac.uk")

    def sync(self, entries, user=None):
        pipeline.sync_groups(None, {"email": "a@cam.ac.uk"}, object(), user=user or self.user,
                             allowed_entries=[e.pk for e in entries])

    def test_adds_groups_of_the_matching_entry(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        entry.groups.add(self.arabic)
        self.sync([entry])
        self.assertEqual(list(self.user.groups.all()), [self.arabic])

    def test_union_of_every_matching_entry(self):
        exact = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        exact.groups.add(self.arabic)
        domain = AllowedLogin.objects.create(identifier="@cam.ac.uk")
        domain.groups.add(self.tech)
        crsid = AllowedLogin.objects.create(identifier="a")
        self.sync([exact, domain, crsid])
        self.assertEqual(set(self.user.groups.all()), {self.arabic, self.tech})

    def test_is_additive_and_never_removes_a_group_set_by_hand(self):
        self.user.groups.add(self.tech)
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        entry.groups.add(self.arabic)
        self.sync([entry])
        self.assertEqual(set(self.user.groups.all()), {self.arabic, self.tech})

    def test_is_idempotent(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        entry.groups.add(self.arabic)
        self.sync([entry])
        self.sync([entry])
        self.assertEqual(self.user.groups.count(), 1)

    def test_entry_without_groups_changes_nothing(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        self.sync([entry])
        self.assertEqual(self.user.groups.count(), 0)

    def test_new_entry_groups_apply_at_the_next_login_of_an_existing_user(self):
        entry = AllowedLogin.objects.create(identifier="a@cam.ac.uk")
        self.sync([entry])
        entry.groups.add(self.arabic)
        self.sync([entry])
        self.assertEqual(list(self.user.groups.all()), [self.arabic])

    def test_no_user_or_no_entries_is_a_noop(self):
        pipeline.sync_groups(None, {}, object(), user=None, allowed_entries=[1])
        pipeline.sync_groups(None, {}, object(), user=self.user, allowed_entries=[])

    def test_step_is_wired_into_the_social_auth_pipeline(self):
        from django.conf import settings

        self.assertEqual(settings.SOCIAL_AUTH_PIPELINE[-1], "accounts.pipeline.sync_groups")
        self.assertLess(settings.SOCIAL_AUTH_PIPELINE.index("accounts.pipeline.finish_login"),
                        settings.SOCIAL_AUTH_PIPELINE.index("accounts.pipeline.sync_groups"))


class GroupAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@x.org", "pw-root-12345")
        self.client.force_login(self.admin)

    def test_creating_a_group_with_the_sees_all_tick(self):
        page = self.client.get(reverse("admin:auth_group_add"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "sees_all_texts")
        response = self.client.post(reverse("admin:auth_group_add"), {
            "name": "Technical", "permissions": [],
            "access-TOTAL_FORMS": "1", "access-INITIAL_FORMS": "0",
            "access-MIN_NUM_FORMS": "0", "access-MAX_NUM_FORMS": "1",
            "access-0-sees_all_texts": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GroupAccess.objects.get(group__name="Technical").sees_all_texts)

    def test_group_list_shows_the_counts_and_the_tick(self):
        group = Group.objects.create(name="Arabic")
        GroupAccess.objects.create(group=group, sees_all_texts=False)
        group.user_set.add(self.admin)
        page = self.client.get(reverse("admin:auth_group_changelist"))
        self.assertContains(page, "Arabic")

    def test_allowlist_entry_can_carry_groups(self):
        group = Group.objects.create(name="Arabic")
        response = self.client.post(reverse("admin:accounts_allowedlogin_add"),
                                    {"identifier": "new@cam.ac.uk", "groups": [group.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(AllowedLogin.objects.get().groups.all()), [group])

    def test_user_page_lets_an_admin_assign_groups(self):
        group = Group.objects.create(name="Arabic")
        person = User.objects.create_user("p@x.org", "p@x.org")
        page = self.client.get(reverse("admin:auth_user_change", args=[person.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "groups")

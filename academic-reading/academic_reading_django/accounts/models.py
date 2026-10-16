from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import models

CAM_DOMAIN = "cam.ac.uk"


class AllowedLogin(models.Model):
    """One allowlist entry: an exact email, a bare CRSid, or an ``@domain``.

    SSO sign-in is refused unless the signed-in email matches at least one entry.
    """

    identifier = models.CharField(
        max_length=255,
        unique=True,
        help_text="An email (abc123@cam.ac.uk), a CRSid (abc123), or a whole domain (@dept.cam.ac.uk).",
    )
    matched_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="allowed_login",
        editable=False,
    )
    groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="allowed_logins",
        help_text="Groups this person is added to at every sign-in (never removed automatically).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["identifier"]

    def __str__(self) -> str:
        return self.identifier

    def save(self, *args, **kwargs) -> None:
        self.identifier = self.identifier.strip().lower()
        super().save(*args, **kwargs)

    def matching_users(self):
        """Existing accounts this entry covers (same rules as ``matches``)."""
        User = get_user_model()
        ident = self.identifier
        if ident.startswith("@"):
            return User.objects.filter(email__iendswith=ident)
        if "@" in ident:
            return User.objects.filter(models.Q(email__iexact=ident) | models.Q(username__iexact=ident))
        return User.objects.filter(email__iexact=f"{ident}@{CAM_DOMAIN}")  # a bare CRSid

    def apply_groups_to_existing_users(self) -> int:
        """Add every matching existing account to this entry's groups; returns how many gained a group.

        Additive only, like the sync at sign-in. People who have not signed in yet have no account;
        they are added when they first sign in.
        """
        groups = list(self.groups.all())
        changed = 0
        if not groups:
            return changed
        for user in self.matching_users():
            have = set(user.groups.values_list("pk", flat=True))
            missing = [g for g in groups if g.pk not in have]
            if missing:
                user.groups.add(*missing)
                changed += 1
        return changed

    @classmethod
    def matches(cls, email: str) -> list["AllowedLogin"]:
        email = (email or "").strip().lower()
        if "@" not in email:
            return []
        local, domain = email.split("@", 1)
        keys = {email, f"@{domain}"}
        if domain == CAM_DOMAIN:
            keys.add(local)
        return list(cls.objects.filter(identifier__in=keys))


class GroupAccess(models.Model):
    """Extra settings for a Django group (one row per group, created on demand)."""

    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="access")
    sees_all_texts = models.BooleanField(
        default=False,
        help_text="Members of this group can read every library text, whatever groups the text is limited to.",
    )

    class Meta:
        verbose_name = "group access"
        verbose_name_plural = "group access"

    def __str__(self) -> str:
        return f"{self.group.name}: {'all texts' if self.sees_all_texts else 'own texts'}"

from django.conf import settings
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["identifier"]

    def __str__(self) -> str:
        return self.identifier

    def save(self, *args, **kwargs) -> None:
        self.identifier = self.identifier.strip().lower()
        super().save(*args, **kwargs)

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

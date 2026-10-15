"""python-social-auth pipeline steps for University Microsoft (Entra ID) SSO.

``enforce_allowlist`` runs right after social-core's ``auth_allowed`` and
refuses the sign-in before any user/social-auth row exists. ``finish_login``
runs last, once a stock ``auth.User`` has been found or created.
"""

from __future__ import annotations

try:  # social-auth-core 6.x renamed AuthForbidden
    from social_core.exceptions import AuthForbidden
except ImportError:  # pragma: no cover
    from social_core.exceptions import AuthPolicyError as AuthForbidden

from .login_report import report_login
from .models import AllowedLogin


class NotAllowlisted(AuthForbidden):
    """SocialAuthExceptionMiddleware surfaces str(exception) as a Django
    message and redirects to SOCIAL_AUTH_LOGIN_ERROR_URL."""

    def __str__(self) -> str:
        return (
            "Your Cambridge account isn't on the allowed list for this "
            "service. Contact your teacher or the Language Centre."
        )


def enforce_allowlist(strategy, details, backend, *args, **kwargs):
    entries = AllowedLogin.matches(details.get("email") or "")
    if not entries:
        raise NotAllowlisted(backend)
    return {"allowed_entries": [entry.pk for entry in entries]}


def finish_login(strategy, details, backend, user=None, allowed_entries=None, *args, **kwargs):
    if user is None:
        return
    if not user.is_active:
        raise AuthForbidden(backend)

    email = (details.get("email") or "").strip().lower()
    if not user.email:
        user.email = email
        user.save(update_fields=["email"])

    # Only a specific (non-domain) entry can belong to one person.
    specific = (
        AllowedLogin.objects.filter(pk__in=allowed_entries or [])
        .exclude(identifier__startswith="@")
        .first()
    )
    if specific and specific.matched_user_id != user.id:
        specific.matched_user = user
        specific.save(update_fields=["matched_user"])

    report_login(email or user.email, "sso")

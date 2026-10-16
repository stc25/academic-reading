from django.conf import settings


def sso_enabled():
    return bool(
        settings.SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY
        and settings.SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET
    )


def sign_in_available():
    """True when the login page offers at least one way to sign in."""
    return sso_enabled() or settings.EMAIL_PASSWORD_LOGIN_ENABLED


def auth_flags(request):
    return {
        "auth_required": settings.AUTH_REQUIRED,
        "sso_enabled": sso_enabled(),
        "password_login_enabled": settings.EMAIL_PASSWORD_LOGIN_ENABLED,
    }

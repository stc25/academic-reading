from django.conf import settings


def auth_flags(request):
    return {
        "auth_required": settings.AUTH_REQUIRED,
        "sso_enabled": bool(
            settings.SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY
            and settings.SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET
        ),
        "password_login_enabled": settings.EMAIL_PASSWORD_LOGIN_ENABLED,
    }

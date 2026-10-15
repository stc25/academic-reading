from django.conf import settings
from django.contrib.auth.views import redirect_to_login

# Path prefixes (after the script prefix) that never require sign-in.
EXEMPT_PREFIXES = ("/health", "/static/", "/django-admin/", "/auth/")


class AuthRequiredMiddleware:
    """When AUTH_REQUIRED is on, send anonymous visitors to the login page.

    The switch is read per request so tests can toggle it; in production it is
    fixed at process start.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.AUTH_REQUIRED
            and not request.user.is_authenticated
            and not request.path_info.startswith(EXEMPT_PREFIXES)
        ):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render
from django.conf import settings

from .context_processors import sign_in_available

# Path prefixes (after the script prefix) that never require sign-in.
EXEMPT_PREFIXES = ("/health", "/static/", "/django-admin/", "/auth/")


class AuthRequiredMiddleware:
    """Sign-in is mandatory: send anonymous visitors to the login page.

    If no sign-in method is configured at all, the login page would be a dead end, so say so
    plainly (503) instead of redirecting to it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path_info.startswith(EXEMPT_PREFIXES):
            if not sign_in_available():
                return render(request, "accounts/sign_in_not_set_up.html", status=503)
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)

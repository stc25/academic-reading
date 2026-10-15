from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import PasswordResetConfirmView
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .login_report import report_login
from .throttle import throttled


def _safe_next(request) -> str:
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse(settings.LOGIN_REDIRECT_URL)


def login_view(request):
    next_url = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(next_url)

    error = ""
    status = 200
    if request.method == "POST" and settings.EMAIL_PASSWORD_LOGIN_ENABLED:
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        if throttled(request, "login", email):
            error, status = "Too many attempts. Please try again later.", 429
        elif email.endswith("cam.ac.uk"):
            error = "Cambridge accounts must use Cambridge sign-in."
        else:
            user = authenticate(request, username=email, password=password)
            if user is not None and user.is_active:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                report_login(user.email or email, "email")
                return redirect(next_url)
            error = "Incorrect email or password."
    return render(request, "accounts/login.html", {"error": error, "next": next_url}, status=status)


@require_POST
def logout_view(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


class PasswordSetView(PasswordResetConfirmView):
    template_name = "accounts/password_set.html"
    success_url = reverse_lazy("accounts:login")

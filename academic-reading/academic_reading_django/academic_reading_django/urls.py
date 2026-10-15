"""Root URL configuration for academic_reading_django."""

from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path


def health_view(request):
    return JsonResponse({"ok": True})


def health_redirect(request):
    return redirect("/health/", permanent=True)


urlpatterns = [
    path("health", health_redirect),
    path("health/", health_view),
    path("django-admin/", admin.site.urls),
    path("auth/sso/", include("social_django.urls", namespace="social")),
    path("auth/", include("accounts.urls")),
    path("", include("reading.urls")),
]

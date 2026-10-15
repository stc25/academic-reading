from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-set/<uidb64>/<token>/", views.PasswordSetView.as_view(), name="password_reset_confirm"),
]

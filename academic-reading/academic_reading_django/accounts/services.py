from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def build_set_password_url(user, request=None) -> str:
    path = reverse(
        "accounts:password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    return request.build_absolute_uri(path) if request is not None else path


def send_account_created_email(user, request=None) -> None:
    """Tell an admin-created user to set their own password (single-use link;
    the password itself is never emailed)."""
    context = {"user": user, "set_password_url": build_set_password_url(user, request)}
    subject = render_to_string("accounts/email/account_created_subject.txt", context).strip()
    message = EmailMultiAlternatives(
        subject,
        render_to_string("accounts/email/account_created.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.attach_alternative(render_to_string("accounts/email/account_created.html", context), "text/html")
    message.send()

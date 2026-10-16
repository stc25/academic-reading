"""Shared test setup: sign-in is mandatory and the library lives in the database."""

import itertools

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client

_counter = itertools.count(1)


def import_library():
    call_command("import_library", verbosity=0)


def new_user(email=None, **extra):
    email = email or f"reader{next(_counter)}@x.org"
    return User.objects.create_user(email, email, **extra)


def signed_in_client(email=None, **extra):
    """A fresh browser signed in as a new user (``client.user`` holds the user)."""
    client = Client()
    client.user = new_user(email, **extra)
    client.force_login(client.user)
    return client


def prepare_reader(testcase, **extra):
    """Import the library and sign ``testcase.client`` in as a new user."""
    import_library()
    testcase.user = new_user(**extra)
    testcase.client.force_login(testcase.user)

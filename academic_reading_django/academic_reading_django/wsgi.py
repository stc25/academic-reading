"""WSGI entry point for academic_reading_django.

Gunicorn is started by docker/entrypoint.sh and configured to import
``academic_reading_django.wsgi:application``.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academic_reading_django.settings")

application = get_wsgi_application()

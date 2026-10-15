#!/usr/bin/env python
"""Django management entry point for academic_reading_django."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academic_reading_django.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - explicit guidance
        raise ImportError(
            "Couldn't import Django. Activate the project's virtualenv "
            "or install the project requirements inside the container."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

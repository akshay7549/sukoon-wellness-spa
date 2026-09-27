
#!/usr/bin/env python
"""
Django's command-line utility for administrative tasks.
"""

import os
import sys


def main():
    """
    Run administrative tasks.
    """

    # =========================================================
    # DJANGO SETTINGS
    # =========================================================

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "config.settings",
    )

    # =========================================================
    # IMPORT DJANGO
    # =========================================================

    try:
        from django.core.management import (
            execute_from_command_line,
        )

    except ImportError as exc:

        raise ImportError(
            "Couldn't import Django. Make sure Django is "
            "installed and the virtual environment is activated."
        ) from exc

    # =========================================================
    # EXECUTE COMMAND
    # =========================================================

    execute_from_command_line(sys.argv)


# =============================================================
# ENTRY POINT
# =============================================================

if __name__ == "__main__":
    main()

"""WSGI config for the ecommerce project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce.settings")

application = get_wsgi_application()

# Pending migrations are applied here so that a deploy which only sets a start
# command still ends up with a correct database. See ecommerce/startup.py.
from ecommerce.startup import run_startup_tasks  # noqa: E402  (needs Django set up first)

run_startup_tasks()

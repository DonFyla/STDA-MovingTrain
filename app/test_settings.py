import os

# Set a test-only secret key before importing base settings, which require one.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

# Force SQLite for tests so a PostgreSQL client is not required locally.
os.environ["DATABASE_URL"] = ""

from .settings import *  # noqa: F401,F403

# Use local-memory cache for tests so Redis is not required.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

ALLOWED_HOSTS = ["*"]

# Dummy Flutterwave secrets so webhook signature tests run without env vars.
FLUTTERWAVE_SECRET_KEY = "FLWSECK_TEST-dummy_secret_key_for_tests_only"
FLUTTERWAVE_PUBLIC_KEY = "FLWPUBK_TEST-dummy_public_key_for_tests_only"
FLUTTERWAVE_WEBHOOK_SECRET = "whsec_dummy_webhook_secret_for_tests_only"

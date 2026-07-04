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

# Dummy Paystack secret so webhook signature tests run without env vars.
PAYSTACK_SECRET_KEY = "sk_test_dummy_secret_key_for_tests_only"

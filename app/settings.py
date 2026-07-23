"""
Django settings for Chess Academy.
"""

from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "django_extensions",
    "widget_tweaks",
    "ckeditor",
    "ckeditor_uploader",
    # Local apps
    "web",
    "accounts",
    "quiz",
    "scheduling",
    "payments",
    "admin_portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
]

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context_processors.navigation",
                "web.context_processors.seo",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"

# Database
DATABASE_URL = config("DATABASE_URL", default=None)

if DATABASE_URL:
    import dj_database_url

    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Redis
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")

# Caches
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Sessions
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

from django.urls import reverse_lazy


# Authentication
LOGIN_URL = reverse_lazy("accounts:login")
LOGIN_REDIRECT_URL = reverse_lazy("accounts:dashboard")


# Static files
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
CKEDITOR_UPLOAD_PATH = "uploads/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Silence known warnings
# TODO: Migrate from django-ckeditor (CKEditor 4) to a maintained editor
# (e.g., django-ckeditor-5 or a plain textarea) to resolve the security warning.
SILENCED_SYSTEM_CHECKS = ["ckeditor.W001"]

# CKEditor
CKEDITOR_CONFIGS = {
    "default": {
        "toolbar": "full",
        "height": 300,
        "width": "100%",
    },
}

# Email
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="bookings@themovingtrain.org")

# Flutterwave
FLUTTERWAVE_SECRET_KEY = config("FLUTTERWAVE_SECRET_KEY", default="")
FLUTTERWAVE_PUBLIC_KEY = config("FLUTTERWAVE_PUBLIC_KEY", default="")
FLUTTERWAVE_WEBHOOK_SECRET = config("FLUTTERWAVE_WEBHOOK_SECRET", default="")

# Google Tags / Ads (optional; loaded in base template when set)
GOOGLE_TAG_MANAGER_ID = config("GOOGLE_TAG_MANAGER_ID", default="")
GOOGLE_ANALYTICS_ID = config("GOOGLE_ANALYTICS_ID", default="")
GOOGLE_ADS_CONVERSION_ID = config("GOOGLE_ADS_CONVERSION_ID", default="")
GOOGLE_ADS_CONVERSION_LABEL = config("GOOGLE_ADS_CONVERSION_LABEL", default="")

# Default brand metadata for SEO
SITE_NAME = "Moving Train Chess Academy"
SITE_DOMAIN = config("SITE_DOMAIN", default="themovingtrain.org")
SITE_DEFAULT_IMAGE = config(
    "SITE_DEFAULT_IMAGE", default="static/images/others/logo.svg"
)

# Security headers (enable in production)
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Reverse proxy settings (required when running behind Nginx on Contabo)
USE_X_FORWARDED_HOST = config("USE_X_FORWARDED_HOST", default=True, cast=bool)
USE_X_FORWARDED_PORT = config("USE_X_FORWARDED_PORT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
}

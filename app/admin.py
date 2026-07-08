from django.contrib import admin
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit


# Rate-limit the default admin login view without replacing the admin site,
# so all existing @admin.register() decorators continue to work.
admin.site.login = method_decorator(
    ratelimit(key="ip", rate="5/m", method="POST", block=True),
    name="login",
)(admin.site.login)

site = admin.site

__all__ = ["site"]

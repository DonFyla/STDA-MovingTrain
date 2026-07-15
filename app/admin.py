from django.contrib import admin
from django.http import HttpResponseForbidden
from django_ratelimit.core import is_ratelimited


class RateLimitedAdminSite(admin.AdminSite):
    """Custom admin site with IP-based rate limiting on login."""

    def login(self, request, extra_context=None):
        if request.method == "POST":
            if is_ratelimited(
                request=request,
                group="admin_login",
                key="ip",
                rate="5/m",
                method="POST",
                increment=True,
            ):
                return HttpResponseForbidden(
                    "Too many login attempts. Try again later."
                )
        return super().login(request, extra_context=extra_context)


site = RateLimitedAdminSite(name="admin")

# Re-register any models already registered on the default admin site.
for model, admin_class in admin.site._registry.items():
    site.register(model, admin_class.__class__)

__all__ = ["site"]

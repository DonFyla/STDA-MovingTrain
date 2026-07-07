"""
URL configuration for app project.
"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.views.generic.base import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from app.admin import site as admin_site
from web.sitemaps import StaticViewSitemap, CourseSitemap

sitemaps = {
    "static": StaticViewSitemap,
    "courses": CourseSitemap,
}

urlpatterns = [
    path("admin/", admin_site.urls),
    path("ckeditor/", include("ckeditor_uploader.urls")),
    path("", include("web.urls")),
    path("accounts/", include("accounts.urls")),
    path("quiz/", include("quiz.urls")),
    path("scheduling/", include("scheduling.urls")),
    path("payments/", include("payments.urls")),
    path("admin-portal/", include("admin_portal.urls")),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots_txt",
    ),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

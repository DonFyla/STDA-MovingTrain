"""
URL configuration for app project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from app.admin import site as admin_site

urlpatterns = [
    path("admin/", admin_site.urls),
    path("ckeditor/", include("ckeditor_uploader.urls")),
    path("", include("web.urls")),
    path("accounts/", include("accounts.urls")),
    path("quiz/", include("quiz.urls")),
    path("scheduling/", include("scheduling.urls")),
    path("payments/", include("payments.urls")),
    path("admin-portal/", include("admin_portal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

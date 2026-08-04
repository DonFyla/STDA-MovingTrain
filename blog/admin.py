from django.contrib import admin
from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "status", "published_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "body"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["author", "published_at", "created_at", "updated_at"]

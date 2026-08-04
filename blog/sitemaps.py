from django.contrib.sitemaps import Sitemap
from .models import Post


class PostSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return Post.objects.filter(status=Post.STATUS_PUBLISHED)

    def lastmod(self, obj):
        return obj.updated_at

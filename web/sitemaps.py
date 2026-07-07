from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from web.data import COURSE_CURRICULA


class StaticViewSitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return ["home", "courses", "tutors", "gallery", "quiz:register"]

    def location(self, item):
        return reverse(item)


class CourseSitemap(Sitemap):
    priority = 0.9
    changefreq = "monthly"

    def items(self):
        return list(COURSE_CURRICULA.keys())

    def location(self, item):
        return reverse("course_detail", kwargs={"slug": item})

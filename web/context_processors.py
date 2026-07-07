from django.conf import settings


def navigation(request):
    path = request.path
    items = [
        {"label": "Home", "url": "/", "name": "home"},
        {"label": "About", "url": "/#about-us", "name": "about"},
        {"label": "Courses", "url": "/courses/", "name": "courses"},
        {"label": "Tutors", "url": "/tutors/", "name": "tutors"},
        {"label": "Gallery", "url": "/gallery/", "name": "gallery"},
        {"label": "Quiz", "url": "/quiz/", "name": "quiz"},
    ]

    # Mark active based on path or anchor
    for item in items:
        item["active"] = False
        if item["name"] == "home" and path == "/":
            item["active"] = True
        elif item["url"].rstrip("/") == path.rstrip("/"):
            item["active"] = True

    return {"nav_items": items}


def seo(request):
    """Expose SEO/analytics settings and helpers to every template."""
    scheme = "https" if request.is_secure() else "http"
    canonical_url = f"{scheme}://{request.get_host()}{request.path}"
    return {
        "SITE_NAME": getattr(settings, "SITE_NAME", "Moving Train Chess Academy"),
        "SITE_DOMAIN": getattr(settings, "SITE_DOMAIN", "themovingtrain.org"),
        "GOOGLE_TAG_MANAGER_ID": getattr(settings, "GOOGLE_TAG_MANAGER_ID", ""),
        "GOOGLE_ANALYTICS_ID": getattr(settings, "GOOGLE_ANALYTICS_ID", ""),
        "GOOGLE_ADS_CONVERSION_ID": getattr(settings, "GOOGLE_ADS_CONVERSION_ID", ""),
        "GOOGLE_ADS_CONVERSION_LABEL": getattr(settings, "GOOGLE_ADS_CONVERSION_LABEL", ""),
        "CANONICAL_URL": canonical_url,
    }

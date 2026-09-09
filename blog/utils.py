from django.conf import settings


def can_publish_blog(user):
    """Whether the user may write blog posts.

    Coaches can always post. Students are gated behind the
    BLOG_ALLOW_STUDENT_POSTS setting so the feature can be enabled
    for them later without a code change.
    """
    if not user.is_authenticated:
        return False
    if user.is_coach:
        return True
    return getattr(settings, "BLOG_ALLOW_STUDENT_POSTS", False)

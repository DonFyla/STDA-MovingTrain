from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveEmailBackend(ModelBackend):
    """Authenticate by email case-insensitively.

    The default ModelBackend matches the USERNAME_FIELD (email) with an exact
    string comparison, so a user who registered as John@gmail.com cannot log
    in as john@gmail.com. Signup lowercases the stored email; this backend
    additionally tolerates any casing at login (and mixed-case legacy rows).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        email = username if username is not None else kwargs.get(User.USERNAME_FIELD)
        if email is None or password is None:
            return None
        # Legacy data may hold near-duplicates differing only by case; take
        # the oldest rather than crashing with MultipleObjectsReturned.
        user = User.objects.filter(email__iexact=email).order_by("date_joined").first()
        if user is None:
            # Match ModelBackend's timing behaviour for unknown users.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

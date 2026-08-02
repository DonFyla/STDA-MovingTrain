import time

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core import signing
from .models import User

# Minimum seconds a human needs to fill the signup form; faster means bot.
MIN_FORM_FILL_SECONDS = 3
# Signed form timestamps older than this are rejected (stale/tampered).
FORM_TS_MAX_AGE_SECONDS = 3600


class CustomUserCreationForm(UserCreationForm):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("coach", "Coach"),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial="student",
        widget=forms.RadioSelect,
        label="I am signing up as a",
    )
    # Honeypot: invisible to humans, auto-filled by bots. Must stay empty.
    company = forms.CharField(
        required=False,
        label="Company",
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
    )
    # Signed render timestamp; rejects instant and stale/forged submissions.
    form_ts = forms.CharField(required=True, widget=forms.HiddenInput)

    class Meta:
        model = User
        fields = ("email", "username", "full_name", "phone", "role")

    def clean_form_ts(self):
        value = self.cleaned_data.get("form_ts", "")
        try:
            ts = float(signing.loads(value, max_age=FORM_TS_MAX_AGE_SECONDS))
        except (signing.BadSignature, signing.SignatureExpired, ValueError):
            raise forms.ValidationError(
                "Something went wrong. Please reload the page and try again."
            )
        if time.time() - ts < MIN_FORM_FILL_SECONDS:
            raise forms.ValidationError(
                "Something went wrong. Please reload the page and try again."
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("company"):
            raise forms.ValidationError(
                "Something went wrong. Please reload the page and try again."
            )
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get("role", "student")
        if role == "coach":
            user.is_coach = True
            user.is_student = False
        else:
            user.is_coach = False
            user.is_student = True
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("coach", "Coach"),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label="Role",
    )

    class Meta:
        model = User
        fields = ("email", "username", "full_name", "phone", "role", "is_coach", "is_student")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["role"].initial = "coach" if self.instance.is_coach else "student"
        # Hide the raw booleans when they are present; the admin may drop them,
        # so check first.
        if "is_coach" in self.fields:
            self.fields["is_coach"].widget = forms.HiddenInput()
        if "is_student" in self.fields:
            self.fields["is_student"].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role", "student")
        if role == "coach":
            cleaned_data["is_coach"] = True
            cleaned_data["is_student"] = False
        else:
            cleaned_data["is_coach"] = False
            cleaned_data["is_student"] = True
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get("role", "student")
        if role == "coach":
            user.is_coach = True
            user.is_student = False
        else:
            user.is_coach = False
            user.is_student = True
        if commit:
            user.save()
            self._create_role_profile(user)
        return user

    def _create_role_profile(self, user):
        from scheduling.models import Coach, Student

        if user.is_coach:
            Coach.objects.get_or_create(
                user=user,
                defaults={
                    "name": user.full_name or user.username or user.email,
                    "email": user.email,
                },
            )
        elif user.is_student:
            Student.objects.get_or_create(
                user=user,
                defaults={"parent_phone": user.phone},
            )

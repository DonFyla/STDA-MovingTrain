from django import forms
from .models import Question, Questionnaire, Qtaker, Options


class QtakerForm(forms.ModelForm):
    class Meta:
        model = Qtaker
        fields = ["name", "age", "email", "skill"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Your name"}),
            "age": forms.NumberInput(attrs={"class": "form-input", "placeholder": "Your age"}),
            "email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "your@email.com"}),
            "skill": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["age"].required = False
        if user:
            self.fields["name"].initial = user.full_name or user.get_full_name() or user.username
            self.fields["email"].initial = user.email


class AnswerForm(forms.Form):
    answer = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Your answer"}),
        required=True,
    )

    def __init__(self, *args, question=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        if question and question.question_type == "radio":
            choices = [
                (opt.id, opt.text)
                for opt in Options.objects.filter(question=question)
            ]
            self.fields["answer"] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect(attrs={"class": "form-radio"}),
                required=True,
            )


class CoachQuestionForm(forms.ModelForm):
    """Form for coaches to submit quiz questions for staff review."""

    option_1 = forms.CharField(required=False, max_length=500)
    option_2 = forms.CharField(required=False, max_length=500)
    option_3 = forms.CharField(required=False, max_length=500)
    option_4 = forms.CharField(required=False, max_length=500)
    correct_option = forms.ChoiceField(
        choices=[("", "---------")] + [(str(i), f"Option {i}") for i in range(1, 5)],
        required=False,
    )
    expected_answer = forms.CharField(required=False, max_length=2000)

    class Meta:
        model = Question
        fields = ["questionnaire", "question_type", "question"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["questionnaire"].queryset = Questionnaire.objects.order_by("title")
        self.fields["question_type"].choices = [
            ("radio", "Single choice"),
            ("text", "Text answer"),
        ]

    def clean(self):
        cleaned_data = super().clean()
        question_type = cleaned_data.get("question_type")

        if question_type == "radio":
            options = [
                (cleaned_data.get(f"option_{i}") or "").strip() for i in range(1, 5)
            ]
            filled = [text for text in options if text]
            if len(filled) < 2:
                raise forms.ValidationError(
                    "Provide at least two answer options for a single-choice question."
                )
            correct_option = cleaned_data.get("correct_option")
            if not correct_option:
                raise forms.ValidationError("Choose which option is the correct answer.")
            if not options[int(correct_option) - 1]:
                raise forms.ValidationError(
                    "The correct option is empty — fill in that option or pick another."
                )
        elif question_type == "text":
            if not (cleaned_data.get("expected_answer") or "").strip():
                raise forms.ValidationError(
                    "Provide the expected answer for a text question."
                )

        return cleaned_data

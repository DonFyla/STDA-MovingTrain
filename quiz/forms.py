from django import forms
from .models import Qtaker, Options


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

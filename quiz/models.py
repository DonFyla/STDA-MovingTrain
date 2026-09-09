from django.db import models
from django.conf import settings
from django_ckeditor_5.fields import CKEditor5Field


class Questionnaire(models.Model):
    QUESTION_MOTIFS =(
        ("mate_in_1", "Mate in 1"),
        ("mate_in_2", "Mate in 2"),
        ("pins", "Pins"),
        ("forks", "Forks"),
        ("skewers", "Skewers"),
        ("discovered_attacks", "Discovered Attacks"),
        ("endgames", "Endgames"),
        ("openings", "Openings"),
        ("tactics", "Tactics"),
    )
    
    QUESTION_GRADES = (
        ("easy", "Easy"),
        ("medium","Medium"),
        ("hard", "Hard")
    )
    title = models.CharField(max_length=255, unique=True)
    motif = models.CharField(choices=QUESTION_MOTIFS, blank=True, default="", max_length=100)
    difficulty = models.CharField(choices=QUESTION_GRADES, blank=True, default="", max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return self.title


class Qtaker(models.Model):
    chess_level = (
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("expert", "Expert"),
    )
    name = models.CharField(null=False, max_length=100)
    age = models.IntegerField(blank=True, null=True)
    email = models.EmailField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_attempts",
    )
    current_question_set = models.JSONField(null=True, blank=True, default=None)
    next_question_set = models.JSONField(null=True, blank=True, default=None)
    date_taken = models.DateTimeField(auto_now_add=True, verbose_name="Event Date and Time")
    skill = models.CharField(choices=chess_level, default="beginner", max_length=100)
    test_result = models.FloatField(null=True)
    current_score = models.IntegerField(default=0)
    scored_question_ids = models.JSONField(default=list, blank=True)
    last_answer_id = models.PositiveIntegerField(null=True, blank=True)
    last_question_id = models.PositiveIntegerField(null=True, blank=True)
    last_text_answer = models.CharField(max_length=2000, blank=True, default="")

    def __str__(self):
        return self.name

    @classmethod
    def get_next_skill(cls, current_skill):
        skills = [choice[0] for choice in cls.chess_level]
        try:
            current_index = skills.index(current_skill)
            if current_index + 1 < len(skills):
                return skills[current_index + 1]
            else:
                return None
        except (IndexError, ValueError):
            return None


class Question(models.Model):
    QUESTION_TYPES = [
        ("text", "Text Answer"),
        ("radio", "Single Choice(checkbox)"),
    ]
                       

    fen = models.CharField(max_length=300, blank=True, default="")
    solution_uci = models.CharField(max_length=10, blank=True, default="")

    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE)
    question_type = models.CharField(
        choices=QUESTION_TYPES, max_length=20, default="radio"
    )
    question = CKEditor5Field("Text", config_name="default")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    placement = models.PositiveIntegerField()
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{str(self.questionnaire)} - Q{self.placement} {self.question}"


class Options(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text = models.TextField()
    correct = models.BooleanField()

    def __str__(self):
        return self.text
    

class QuestionResult(models.Model):
    qtaker = models.ForeignKey(Qtaker,on_delete=models.PROTECT)
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    answer_given = models.CharField(max_length=2000, blank=True, default="")
    correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)


class Badge(models.Model):
    """A badge in the catalogue. motif/difficulty badges are auto-provisioned
    with slugs of the form 'motif-<motif>-<difficulty>' (see quiz/badges.py)."""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=10, default="🏅")  # emoji
    motif = models.CharField(choices=Questionnaire.QUESTION_MOTIFS, max_length=100, blank=True, default="")
    difficulty = models.CharField(choices=Questionnaire.QUESTION_GRADES, max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    """A badge awarded to a user. qtaker is the evidence of the feat."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    qtaker = models.ForeignKey(Qtaker, on_delete=models.SET_NULL, null=True, blank=True)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "badge"]

    def __str__(self):
        return f"{self.user} — {self.badge}"


class Activity(models.Model):
    """One feed event (badge earned, level up). Text is frozen at write time —
    templates render it verbatim. Design ref: docs/chess-proficiency-design.md §6.2."""
    KINDS = [
        ("badge", "Badge earned"),
        ("level_up", "Level up"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    kind = models.CharField(choices=KINDS, max_length=20)
    badge = models.ForeignKey(Badge, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.user.username}: {self.text}"

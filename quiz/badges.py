"""Badge evaluation. Design reference: docs/chess-proficiency-design.md §3.6.

evaluate_badges(qtaker) is called from quiz_result_view after a quiz is graded.
Motif badges are auto-provisioned on first award: passing (> PASS_PERCENTAGE) a
quiz whose questionnaire is tagged with motif + difficulty grants the badge
slugged 'motif-<motif>-<difficulty>'.
"""

from .models import Badge, Questionnaire, QuestionResult, UserBadge
from .views import PASS_PERCENTAGE

DIFFICULTY_ICONS = {"easy": "🥉", "medium": "🥈", "hard": "🥇"}


def _motif_badge_slug(motif, difficulty):
    return f"motif-{motif}-{difficulty}"


def _get_or_provision_motif_badge(motif, difficulty):
    badge, _ = Badge.objects.get_or_create(
        slug=_motif_badge_slug(motif, difficulty),
        defaults={
            "name": f"{dict(Questionnaire.QUESTION_MOTIFS)[motif]} — {dict(Questionnaire.QUESTION_GRADES)[difficulty]}",
            "description": f"Passed the {dict(Questionnaire.QUESTION_MOTIFS)[motif]} quiz at {difficulty} difficulty.",
            "icon": DIFFICULTY_ICONS.get(difficulty, "🏅"),
            "motif": motif,
            "difficulty": difficulty,
        },
    )
    return badge


def evaluate_badges(qtaker):
    """Grant any badges earned by this quiz session. Returns newly awarded badges."""
    if qtaker.user_id is None or qtaker.test_result is None:
        return []
    if qtaker.test_result <= PASS_PERCENTAGE:
        return []

    first_result = (
        QuestionResult.objects.filter(qtaker=qtaker, question__isnull=False)
        .select_related("question__questionnaire")
        .first()
    )
    if first_result is None:
        return []

    questionnaire = first_result.question.questionnaire
    motif, difficulty = questionnaire.motif, questionnaire.difficulty
    if not motif or not difficulty:
        return []  # legacy quiz — no badges

    badge = _get_or_provision_motif_badge(motif, difficulty)
    _, created = UserBadge.objects.get_or_create(
        user=qtaker.user, badge=badge, defaults={"qtaker": qtaker}
    )
    return [badge] if created else []

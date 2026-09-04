"""Per-motif proficiency aggregation for the student dashboard chart.

Design reference: docs/chess-proficiency-design.md §3.5.
Level rule: passing (> PASS_PERCENTAGE) a motif quiz at a difficulty means that
level is "achieved"; the chart shows the highest achieved difficulty per motif.
"""

from .models import Questionnaire, QuestionResult
from .views import PASS_PERCENTAGE

# Ordered difficulty ladder — index doubles as the chart value (0 = not attempted).
LEVELS = ["easy", "medium", "hard"]


def get_proficiency(user):
    """Return one dict per motif describing the user's current level.

    Each entry: {"motif", "label", "level" (highest difficulty passed or None),
    "level_value" (0-3 for the chart), "attempts", "best_score"}.
    Untagged (legacy) questionnaires are excluded — see design doc §7.
    """
    results = (
        QuestionResult.objects.filter(qtaker__user=user, question__isnull=False)
        .select_related("question__questionnaire", "qtaker")
    )

    # Group results by (motif, difficulty), tracking sessions and best score.
    pairs = {}
    for result in results:
        questionnaire = result.question.questionnaire
        motif = questionnaire.motif
        difficulty = questionnaire.difficulty
        if not motif or not difficulty:
            continue  # legacy questionnaire — not part of the proficiency chart

        pair = pairs.setdefault((motif, difficulty), {"sessions": set(), "best_score": 0.0})
        qtaker = result.qtaker
        if qtaker.id not in pair["sessions"]:
            pair["sessions"].add(qtaker.id)
            if qtaker.test_result is not None:
                pair["best_score"] = max(pair["best_score"], qtaker.test_result)

    stats = {}
    for (motif, difficulty), pair in pairs.items():
        motif_stats = stats.setdefault(motif, {"attempts": 0, "best_score": 0.0, "passed": set()})
        motif_stats["attempts"] += len(pair["sessions"])
        motif_stats["best_score"] = max(motif_stats["best_score"], pair["best_score"])
        if pair["best_score"] > PASS_PERCENTAGE:
            motif_stats["passed"].add(difficulty)

    proficiency = []
    for value, label in Questionnaire.QUESTION_MOTIFS:
        motif_stats = stats.get(value)
        if motif_stats is None:
            proficiency.append({
                "motif": value, "label": label, "level": None,
                "level_value": 0, "attempts": 0, "best_score": 0.0,
            })
            continue

        passed_indexes = [LEVELS.index(d) for d in motif_stats["passed"] if d in LEVELS]
        highest = max(passed_indexes) if passed_indexes else None
        proficiency.append({
            "motif": value,
            "label": label,
            "level": LEVELS[highest] if highest is not None else None,
            "level_value": (highest + 1) if highest is not None else 0,
            "attempts": motif_stats["attempts"],
            "best_score": round(motif_stats["best_score"], 1),
        })

    return proficiency

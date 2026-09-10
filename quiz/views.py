import chess
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.http import Http404
from .models import Questionnaire, Question, Qtaker, Options, QuestionResult, Activity
from .forms import CoachQuestionForm, QtakerForm, AnswerForm


QUESTIONS_PER_SESSION = 5
PASS_PERCENTAGE = 60


def _owns_quiz_attempt(request, qtaker):
    """Return True if the request is allowed to access this quiz attempt."""
    if qtaker.user_id and request.user.is_authenticated:
        return qtaker.user_id == request.user.id
    # Anonymous attempts are tied to the session that created them.
    session_ids = request.session.get("quiz_qtaker_ids", [])
    return str(qtaker.id) in session_ids or qtaker.id in session_ids


def _register_quiz_attempt(request, qtaker):
    """Store the qtaker id in session so anonymous users can continue their attempt."""
    session_ids = request.session.get("quiz_qtaker_ids", [])
    if qtaker.id not in session_ids:
        session_ids.append(qtaker.id)
        request.session["quiz_qtaker_ids"] = session_ids


def _build_session(qtaker, questionnaire):
    """Build a randomized question session for a qtaker if needed."""
    all_questions = Question.objects.filter(questionnaire=questionnaire, is_approved=True)
    if not all_questions.exists():
        return None
    question_count = all_questions.count()
    questions_to_take = min(QUESTIONS_PER_SESSION, question_count)
    # Evaluate the sliced QuerySet to a list to avoid SQLite randomisation quirks
    randomized_questions = list(all_questions.order_by("?")[:questions_to_take])
    randomized_question_ids = [q.id for q in randomized_questions]
    qtaker.current_question_set = randomized_question_ids
    qtaker.current_score = 0
    qtaker.next_question_set = []
    qtaker.save(update_fields=["current_question_set", "current_score", "next_question_set"])
    return randomized_question_ids


def _text_answer_is_correct(question, answer_text):
    """Return True if the supplied text matches any of the question's correct options."""
    if not answer_text:
        return False
    cleaned = answer_text.strip().lower()
    correct_texts = (
        Options.objects.filter(question=question, correct=True)
        .values_list("text", flat=True)
    )
    return any(cleaned == text.strip().lower() for text in correct_texts)


def _mate_in_one_is_satisfied(question, uci):
    """True if the supplied move is legal and delivers immediate checkmate.

    Lichess records a single solution line, but mate-in-1 puzzles can have
    several mating moves (e.g. promoting to either a rook or a queen), so
    grade by outcome rather than exact move equality."""
    try:
        board = chess.Board(question.fen)
        move = chess.Move.from_uci(uci)
    except ValueError:
        return False
    if move not in board.legal_moves:
        return False
    board.push(move)
    return board.is_checkmate()


def _answer_is_correct(question, answer_text):
    """Grade a text/board answer: exact UCI match against solution_uci when set,
    otherwise any correct option text (covers SAN and UCI for imported puzzles).
    Mate-in-1 also accepts any other move that checkmates."""
    cleaned = (answer_text or "").strip().lower()
    if not cleaned:
        return False
    if question.solution_uci:
        if cleaned == question.solution_uci.strip().lower():
            return True
        if question.questionnaire.motif == "mate_in_1":
            return _mate_in_one_is_satisfied(question, cleaned)
    return _text_answer_is_correct(question, answer_text)


def _start_quiz_for_user(request, user, skill="beginner"):
    """Create a Qtaker for an authenticated user and redirect to first question."""
    qtaker = Qtaker.objects.create(
        name=user.full_name or user.get_full_name() or user.username or user.email,
        email=user.email,
        user=user,
        skill=skill,
    )
    _register_quiz_attempt(request, qtaker)

    try:
        questionnaire = Questionnaire.objects.get(title=skill)
    except Questionnaire.DoesNotExist:
        messages.error(request, f"No questionnaire found for skill level: {skill}")
        return None

    session = _build_session(qtaker, questionnaire)
    if not session:
        messages.error(request, f"No questions found for skill level: {skill}")
        return None

    return qtaker, session[0]

@login_required
def motif_quiz_view(request, motif, difficulty):
    """Start a quiz session for a specific (motif, difficulty) pair."""
    questionnaire = Questionnaire.objects.filter(motif=motif, difficulty=difficulty).first()
    if questionnaire is None:
        messages.error(request, f"No quiz found for {motif} ({difficulty}).")
        return redirect("quiz:register")

    qtaker = Qtaker.objects.create(
        name=request.user.full_name or request.user.get_full_name() or request.user.username or request.user.email,
        email=request.user.email,
        user=request.user,
    )
    _register_quiz_attempt(request, qtaker)

    session = _build_session(qtaker, questionnaire)
    if not session:
        messages.error(request, f"No approved questions found for {motif} ({difficulty}).")
        return redirect("quiz:register")

    return redirect("quiz:question", qtaker_id=qtaker.id, question_id=session[0])


def qtaker_view(request):
    if request.user.is_authenticated:
        skill = request.GET.get("skill", "beginner")
        result = _start_quiz_for_user(request, request.user, skill=skill)
        if result:
            qtaker, first_question_id = result
            return redirect("quiz:question", qtaker_id=qtaker.id, question_id=first_question_id)
        # Fall through to form if quiz cannot be started

    if request.method == "POST":
        form = QtakerForm(request.POST, user=request.user if request.user.is_authenticated else None)
        if form.is_valid():
            qtaker = form.save(commit=False)
            if request.user.is_authenticated:
                qtaker.user = request.user
            qtaker.save()
            _register_quiz_attempt(request, qtaker)
            skill = qtaker.skill
            try:
                questionnaire = Questionnaire.objects.get(title=skill)
            except Questionnaire.DoesNotExist:
                messages.error(
                    request, f"No questionnaire found for skill level: {skill}"
                )
                return render(request, "quiz/register.html", {"form": form})

            session = _build_session(qtaker, questionnaire)
            if not session:
                messages.error(
                    request, f"No questions found for skill level: {skill}"
                )
                return render(request, "quiz/register.html", {"form": form})

            first_question_id = session[0]
            return redirect("quiz:question", qtaker_id=qtaker.id, question_id=first_question_id)
    else:
        form = QtakerForm(user=request.user if request.user.is_authenticated else None)

    return render(request, "quiz/register.html", {"form": form})


def quiz_question_view(request, qtaker_id, question_id):
    qtaker = get_object_or_404(Qtaker, id=qtaker_id)
    if not _owns_quiz_attempt(request, qtaker):
        raise PermissionDenied
    # Derive the questionnaire from the question itself: motif quizzes keep the
    # default skill on the qtaker, so looking up by skill title would find the
    # wrong (legacy) questionnaire and 404.
    question = get_object_or_404(Question, id=question_id)
    questionnaire = question.questionnaire

    # Handle session transition from a previously completed questionnaire
    current_set = qtaker.current_question_set or []
    next_set = qtaker.next_question_set or []

    if next_set and question.id in next_set:
        # Promote next_question_set to current_question_set
        qtaker.current_question_set = next_set
        qtaker.next_question_set = []
        qtaker.save(update_fields=["current_question_set", "next_question_set"])
        question_ids = next_set
    elif current_set and question.id in current_set:
        question_ids = current_set
    elif not current_set and not next_set:
        # No session exists yet — build one
        question_ids = _build_session(qtaker, questionnaire) or []
    else:
        messages.error(request, "This question is not part of your current session.")
        return redirect("quiz:register")

    if question.id not in question_ids:
        messages.error(request, "This question is not part of your current session.")
        return redirect("quiz:register")

    current_index = question_ids.index(question.id)
    next_question_id = (
        question_ids[current_index + 1]
        if current_index + 1 < len(question_ids)
        else None
    )

    if request.method == "POST":
        form = AnswerForm(request.POST, question=question)
        if form.is_valid():
            answer_value = form.cleaned_data["answer"]
            stored_answer_id = 0
            stored_text_answer = ""
            is_correct = False

            if question.question_type == "radio":
                chosen_opt = get_object_or_404(
                    Options, pk=int(answer_value), question=question
                )
                is_correct = chosen_opt.correct
                stored_answer_id = chosen_opt.id
            elif question.question_type == "text":
                is_correct = _answer_is_correct(question, answer_value)
                stored_text_answer = answer_value.strip()

            qtaker.last_answer_id = stored_answer_id
            qtaker.last_question_id = question.id
            qtaker.last_text_answer = stored_text_answer
            qtaker.save(
                update_fields=["last_answer_id", "last_question_id", "last_text_answer"]
            )

            # Scoring is applied when viewing the answer details page.
            return redirect(
                "quiz:answer",
                qtaker_id=qtaker.id,
                answer_id=stored_answer_id,
            )
    else:
        form = AnswerForm(question=question)

    context = {
        "qtaker": qtaker,
        "question": question,
        "form": form,
        "next_question_id": next_question_id,
        "progress": {
            "current": question_ids.index(question.id) + 1,
            "total": len(question_ids),
        },
    }
    return render(request, "quiz/question.html", context)


def quiz_answer_view(request, qtaker_id, answer_id):
    qtaker = get_object_or_404(Qtaker, id=qtaker_id)
    if not _owns_quiz_attempt(request, qtaker):
        raise PermissionDenied
    answer_id_int = int(answer_id)

    if answer_id_int == 0:
        # Text answer
        if not qtaker.last_question_id:
            messages.error(request, "No question answer was recorded.")
            return redirect("quiz:register")
        question = get_object_or_404(Question, id=qtaker.last_question_id)
        user_answer_text = qtaker.last_text_answer
        is_correct = _answer_is_correct(question, user_answer_text)
        chosen_answer = {"id": 0, "text": user_answer_text, "correct": is_correct}
    else:
        chosen_answer_obj = get_object_or_404(Options, pk=answer_id_int)
        question = chosen_answer_obj.question
        is_correct = chosen_answer_obj.correct
        chosen_answer = {
            "id": chosen_answer_obj.id,
            "text": chosen_answer_obj.text,
            "correct": chosen_answer_obj.correct,
        }

    # Record the outcome once per question; the first attempt stands even if the
    # student revisits or re-answers the question page.
    if not QuestionResult.objects.filter(qtaker=qtaker, question=question).exists():
        QuestionResult.objects.create(
            qtaker=qtaker,
            question=question,
            correct=is_correct,
            answer_given=chosen_answer["text"] or "",
        )

    scored_ids = qtaker.scored_question_ids or []
    already_scored = question.id in scored_ids

    if is_correct and not already_scored:
        qtaker.current_score += 1
        scored_ids.append(question.id)
        qtaker.scored_question_ids = scored_ids
        qtaker.save(update_fields=["current_score", "scored_question_ids"])

    correct_answer = Options.objects.filter(question=question, correct=True).first()

    question_ids = qtaker.current_question_set or []
    next_question_id = None
    if question_ids and question.id in question_ids:
        idx = question_ids.index(question.id)
        next_question_id = (
            question_ids[idx + 1] if idx + 1 < len(question_ids) else None
        )

    context = {
        "qtaker": qtaker,
        "question": question,
        "chosen_answer": chosen_answer,
        "correct_answer": correct_answer,
        "is_correct": is_correct,
        "score": qtaker.current_score,
        "next_question_id": next_question_id,
        "progress": {
            "current": question_ids.index(question.id) + 1 if question.id in question_ids else 1,
            "total": len(question_ids) or 1,
        },
    }
    return render(request, "quiz/answer.html", context)


def _prepare_next_session(qtaker, questionnaire):
    """Queue a questionnaire's approved questions as the qtaker's next session."""
    all_questions = Question.objects.filter(questionnaire=questionnaire, is_approved=True)
    if not all_questions.exists():
        return None
    questions_to_take = min(QUESTIONS_PER_SESSION, all_questions.count())
    randomized = list(all_questions.order_by("?")[:questions_to_take])
    qtaker.next_question_set = [q.id for q in randomized]
    qtaker.current_question_set = []
    return {
        "id": questionnaire.id,
        "title": questionnaire.title,
        "first_question_id": randomized[0].id,
    }


def _get_session_questionnaire(qtaker):
    """The questionnaire this session drew its questions from, if identifiable.

    Results accumulate on a qtaker across sessions (a passed quiz queues the
    next session on the same qtaker), so restrict the lookup to results whose
    questions belong to the current session — otherwise passing medium would
    read the questionnaire of the previous (easy) session and offer medium
    again."""
    current = qtaker.current_question_set or []
    first_result = (
        QuestionResult.objects.filter(
            qtaker=qtaker, question__isnull=False, question_id__in=current
        )
        .select_related("question__questionnaire")
        .first()
    )
    if first_result:
        return first_result.question.questionnaire
    if current:
        question = Question.objects.filter(id=current[0]).select_related("questionnaire").first()
        if question:
            return question.questionnaire
    return None


DIFFICULTY_LADDER = ["easy", "medium", "hard"]


def _next_difficulty(difficulty):
    try:
        return DIFFICULTY_LADDER[DIFFICULTY_LADDER.index(difficulty) + 1]
    except (ValueError, IndexError):
        return None


def quiz_result_view(request, qtaker_id):
    qtaker = get_object_or_404(Qtaker, id=qtaker_id)
    if not _owns_quiz_attempt(request, qtaker):
        raise PermissionDenied
    original_skill = qtaker.skill

    if qtaker.current_question_set:
        total_questions = len(qtaker.current_question_set)
    else:
        # Legacy fallback only — motif quizzes always have a current_question_set,
        # and their qtaker.skill is just the default, not a questionnaire title.
        questionnaire = get_object_or_404(Questionnaire, title=original_skill)
        total_questions = Question.objects.filter(
            questionnaire=questionnaire, is_approved=True
        ).count()

    percent = (
        (qtaker.current_score * 100 / total_questions)
        if total_questions > 0
        else 0
    )
    qtaker.test_result = percent
    passed = percent > PASS_PERCENTAGE
    next_questionnaire_data = None
    session_questionnaire = _get_session_questionnaire(qtaker)

    if passed:
        if session_questionnaire and session_questionnaire.motif:
            # Motif quiz: progress to the same motif at the next difficulty.
            next_difficulty = _next_difficulty(session_questionnaire.difficulty)
            if next_difficulty:
                next_questionnaire = Questionnaire.objects.filter(
                    motif=session_questionnaire.motif, difficulty=next_difficulty
                ).first()
                if next_questionnaire:
                    next_questionnaire_data = _prepare_next_session(qtaker, next_questionnaire)
        else:
            # Legacy flow: progress through skill levels by questionnaire title.
            next_skill = Qtaker.get_next_skill(original_skill)
            if next_skill:
                try:
                    next_questionnaire = Questionnaire.objects.get(title=next_skill)
                    next_questionnaire_data = _prepare_next_session(qtaker, next_questionnaire)
                except Questionnaire.DoesNotExist:
                    pass
                qtaker.skill = next_skill

    if next_questionnaire_data is None:
        # No next session (failed quiz, top of the ladder, or next
        # questionnaire has no approved questions) — clear any queued set.
        qtaker.next_question_set = []

    score_for_template = qtaker.current_score
    qtaker.current_score = 0
    qtaker.save(
        update_fields=["test_result", "current_score", "next_question_set", "current_question_set", "skill"]
    )

    if passed:
        from .badges import evaluate_badges
        for badge in evaluate_badges(qtaker):
            messages.success(request, f"Badge earned: {badge.icon} {badge.name}!")
            Activity.objects.create(
                user=qtaker.user,
                kind="badge",
                badge=badge,
                text=f"earned the {badge.icon} {badge.name} badge",
            )
        _record_level_up_activity(qtaker, session_questionnaire)

    context = {
        "qtaker": qtaker,
        "score": score_for_template,
        "total_questions": total_questions,
        "percentage": percent,
        "passed": passed,
        "next_questionnaire": next_questionnaire_data,
        "course_slug": None if (session_questionnaire and session_questionnaire.motif) else qtaker.skill,
        "quiz_url": request.build_absolute_uri(reverse("quiz:register")),
        "result_share_text": f"I scored {percent:.0f}% on the Moving Train Chess Quiz! Can you beat me?",
    }
    return render(request, "quiz/result.html", context)


@login_required
def submit_question_view(request):
    """Allow coaches to submit quiz questions for staff review."""
    if not request.user.is_coach:
        messages.error(request, "Only coach accounts can submit quiz questions.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = CoachQuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.created_by = request.user
            question.is_approved = False
            max_placement = (
                Question.objects.filter(questionnaire=question.questionnaire)
                .aggregate(Max("placement"))["placement__max"]
                or 0
            )
            question.placement = max_placement + 1
            question.save()

            if question.question_type == "radio":
                correct_option = form.cleaned_data["correct_option"]
                for i in range(1, 5):
                    text = (form.cleaned_data.get(f"option_{i}") or "").strip()
                    if text:
                        Options.objects.create(
                            question=question,
                            text=text,
                            correct=(str(i) == correct_option),
                        )
            else:
                Options.objects.create(
                    question=question,
                    text=form.cleaned_data["expected_answer"].strip(),
                    correct=True,
                )

            messages.success(
                request,
                "Question submitted for review. It will appear in quizzes once approved.",
            )
            return redirect("scheduling:coach_dashboard")
    else:
        form = CoachQuestionForm()

    return render(
        request,
        "quiz/submit_question.html",
        {"form": form, "option_fields": [form[f"option_{i}"] for i in range(1, 5)]},
    )


def _record_level_up_activity(qtaker, questionnaire):
    """Write a feed event the first time this user passes a (motif, difficulty).

    Retakes of an already-passed level produce nothing; passing a higher
    difficulty does (it is a different (motif, difficulty) pair)."""
    if qtaker.user_id is None or questionnaire is None:
        return
    motif, difficulty = questionnaire.motif, questionnaire.difficulty
    if not motif or not difficulty:
        return  # legacy quiz — no level-ups
    previously_passed = Qtaker.objects.filter(
        user=qtaker.user,
        test_result__gt=PASS_PERCENTAGE,
        questionresult__question__questionnaire__motif=motif,
        questionresult__question__questionnaire__difficulty=difficulty,
    ).exclude(pk=qtaker.pk).exists()
    if previously_passed:
        return
    motif_label = dict(Questionnaire.QUESTION_MOTIFS)[motif]
    difficulty_label = dict(Questionnaire.QUESTION_GRADES)[difficulty]
    Activity.objects.create(
        user=qtaker.user,
        kind="level_up",
        text=f"reached {difficulty_label} in {motif_label} for the first time ⭐",
    )


@login_required
def feed_view(request):
    """Activity feed: badge awards and level-ups across all students.

    Logged-in users only; students identified by username (privacy decision,
    design doc §6.2)."""
    activities = Activity.objects.select_related("user", "badge")[:100]
    return render(request, "quiz/feed.html", {"activities": activities})


@login_required
def leaderboard_view(request, motif):
    """Per-motif leaderboard. Ranked by level (highest difficulty passed),
    then best score, then fewest attempts. Anonymous attempts excluded;
    usernames only. Design doc §6.2."""
    motif_labels = dict(Questionnaire.QUESTION_MOTIFS)
    if motif not in motif_labels:
        raise Http404("Unknown motif.")

    from .proficiency import LEVELS  # local import: proficiency imports this module

    results = (
        QuestionResult.objects.filter(question__questionnaire__motif=motif)
        .select_related("qtaker", "question__questionnaire")
    )
    rows = {}
    for result in results:
        user = result.qtaker.user
        if user is None:
            continue  # anonymous attempt — excluded from the leaderboard
        row = rows.setdefault(user.id, {"user": user, "best_score": 0.0, "sessions": set(), "passed": set()})
        row["sessions"].add(result.qtaker_id)
        if result.qtaker.test_result is not None:
            row["best_score"] = max(row["best_score"], result.qtaker.test_result)
        pair_difficulty = result.question.questionnaire.difficulty
        if result.qtaker.test_result is not None and result.qtaker.test_result > PASS_PERCENTAGE:
            row["passed"].add(pair_difficulty)

    table = []
    for row in rows.values():
        passed_indexes = [LEVELS.index(d) for d in row["passed"] if d in LEVELS]
        highest = max(passed_indexes) if passed_indexes else None
        table.append({
            "user": row["user"],
            "level": LEVELS[highest] if highest is not None else None,
            "level_value": (highest + 1) if highest is not None else 0,
            "best_score": round(row["best_score"], 1),
            "attempts": len(row["sessions"]),
        })
    table.sort(key=lambda r: (-r["level_value"], -r["best_score"], r["attempts"]))
    table = table[:20]
    for rank, row in enumerate(table, start=1):
        row["rank"] = rank
        row["is_current_user"] = row["user"] == request.user

    return render(request, "quiz/leaderboard.html", {
        "motif": motif,
        "motif_label": motif_labels[motif],
        "motifs": Questionnaire.QUESTION_MOTIFS,
        "rows": table,
    })


@login_required
def leaderboard_index_view(request):
    return redirect("quiz:leaderboard", motif=Questionnaire.QUESTION_MOTIFS[0][0])

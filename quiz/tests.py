from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Questionnaire, Question, Options, Qtaker, QuestionResult, Badge, UserBadge, Activity
from .proficiency import get_proficiency
from .views import _build_session

User = get_user_model()


class QuizTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@example.com"
        )
        self.beginner_questionnaire = Questionnaire.objects.create(
            title="beginner",
            description="Beginner level quiz",
            created_by=self.user,
        )
        self.beginner_question = Question.objects.create(
            questionnaire=self.beginner_questionnaire,
            question="What is the most powerful piece in chess?",
            question_type="radio",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        self.correct_option = Options.objects.create(
            question=self.beginner_question, text="Queen", correct=True
        )
        self.wrong_option = Options.objects.create(
            question=self.beginner_question, text="Pawn", correct=False
        )

        self.intermediate_questionnaire = Questionnaire.objects.create(
            title="intermediate",
            description="Intermediate level quiz",
            created_by=self.user,
        )
        self.intermediate_question = Question.objects.create(
            questionnaire=self.intermediate_questionnaire,
            question="What is a fork?",
            question_type="radio",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        Options.objects.create(
            question=self.intermediate_question,
            text="A piece attacks two or more pieces at once",
            correct=True,
        )
        Options.objects.create(
            question=self.intermediate_question, text="A special pawn move", correct=False
        )

    def _allow_access(self, qtaker):
        """Simulate session ownership for anonymous quiz attempts in tests."""
        session = self.client.session
        session_ids = session.get("quiz_qtaker_ids", [])
        if qtaker.id not in session_ids:
            session_ids.append(qtaker.id)
            session["quiz_qtaker_ids"] = session_ids
            session.save()

    def test_register_page_renders(self):
        response = self.client.get(reverse("quiz:register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "quiz/register.html")

    def test_create_qtaker_redirects_to_first_question(self):
        data = {"name": "Test User", "age": 10, "email": "test@example.com", "skill": "beginner"}
        response = self.client.post(reverse("quiz:register"), data)
        self.assertEqual(response.status_code, 302)
        qtaker = Qtaker.objects.get(email="test@example.com")
        self.assertEqual(qtaker.current_question_set[0], self.beginner_question.id)

    def test_question_page_renders(self):
        qtaker = Qtaker.objects.create(
            name="Test User", age=10, email="test@example.com", skill="beginner"
        )
        qtaker.current_question_set = [self.beginner_question.id]
        qtaker.save()
        self._allow_access(qtaker)

        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, self.beginner_question.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "quiz/question.html")
        self.assertContains(response, "Queen")

    def test_submit_correct_answer(self):
        qtaker = Qtaker.objects.create(
            name="Test User", age=10, email="test@example.com", skill="beginner"
        )
        qtaker.current_question_set = [self.beginner_question.id]
        qtaker.save()
        self._allow_access(qtaker)

        response = self.client.post(
            reverse("quiz:question", args=[qtaker.id, self.beginner_question.id]),
            {"answer": str(self.correct_option.id)},
        )
        self.assertEqual(response.status_code, 302)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.last_answer_id, self.correct_option.id)

    def test_answer_page_renders_and_scores(self):
        qtaker = Qtaker.objects.create(
            name="Test User", age=10, email="test@example.com", skill="beginner"
        )
        qtaker.current_question_set = [self.beginner_question.id]
        qtaker.last_question_id = self.beginner_question.id
        qtaker.last_answer_id = self.correct_option.id
        qtaker.save()
        self._allow_access(qtaker)

        response = self.client.get(
            reverse("quiz:answer", args=[qtaker.id, self.correct_option.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "quiz/answer.html")
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.current_score, 1)

    def test_text_question_with_multiple_correct_options(self):
        """Text questions that accept multiple correct answers should not crash."""
        text_question = Question.objects.create(
            questionnaire=self.beginner_questionnaire,
            question="Name a piece that moves diagonally",
            question_type="text",
            placement=2,
            created_by=self.user,
        )
        Options.objects.create(question=text_question, text="Bishop", correct=True)
        Options.objects.create(question=text_question, text="Queen", correct=True)
        Options.objects.create(question=text_question, text="Knight", correct=False)

        qtaker = Qtaker.objects.create(
            name="Test User", age=10, email="text@example.com", skill="beginner"
        )
        qtaker.current_question_set = [text_question.id]
        qtaker.save()
        self._allow_access(qtaker)

        response = self.client.post(
            reverse("quiz:question", args=[qtaker.id, text_question.id]),
            {"answer": "Queen"},
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.current_score, 1)

    def test_result_page_renders(self):
        qtaker = Qtaker.objects.create(
            name="Test User", age=10, email="test@example.com", skill="beginner"
        )
        qtaker.current_question_set = [self.beginner_question.id]
        qtaker.current_score = 1
        qtaker.save()
        self._allow_access(qtaker)

        response = self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "quiz/result.html")
        self.assertEqual(response.context["score"], 1)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.test_result, 100.0)

    def test_transition_to_next_questionnaire(self):
        """After passing beginner, the user can proceed to intermediate questions."""
        qtaker = Qtaker.objects.create(
            name="Test User", age=10, email="test@example.com", skill="beginner"
        )
        qtaker.current_question_set = [self.beginner_question.id]
        qtaker.current_score = 1
        qtaker.save()
        self._allow_access(qtaker)

        # View result page — this should set next_question_set to intermediate
        response = self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "intermediate")

        qtaker.refresh_from_db()
        self.assertEqual(qtaker.skill, "intermediate")
        self.assertTrue(qtaker.next_question_set)
        intermediate_question_id = qtaker.next_question_set[0]

        # Now request the first intermediate question
        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, intermediate_question_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "quiz/question.html")
        self.assertContains(response, "fork")

        qtaker.refresh_from_db()
        self.assertEqual(qtaker.current_question_set, [intermediate_question_id])
        self.assertEqual(qtaker.next_question_set, [])

    def test_full_multi_level_flow(self):
        """Simulate the complete beginner -> intermediate -> expert flow."""
        user = User.objects.create_user(
            username="leveluser", password="testpass", email="levels@example.com"
        )

        def make_level(title):
            questionnaire, _ = Questionnaire.objects.get_or_create(
                title=title, defaults={"description": f"{title} quiz", "created_by": user}
            )
            # Clear existing questions for this level to ensure count
            Question.objects.filter(questionnaire=questionnaire).delete()
            questions = []
            for i in range(8):
                q = Question.objects.create(
                    questionnaire=questionnaire,
                    question=f"{title} question {i + 1}",
                    question_type="radio",
                    placement=i + 1,
                    created_by=user,
                    is_approved=True,
                )
                Options.objects.create(question=q, text="Correct", correct=True)
                Options.objects.create(question=q, text="Wrong", correct=False)
                questions.append(q)
            return questionnaire, questions

        make_level("beginner")
        make_level("intermediate")
        make_level("expert")

        # Register a beginner qtaker
        response = self.client.post(
            reverse("quiz:register"),
            {"name": "Level Tester", "age": 12, "email": "levels@example.com", "skill": "beginner"},
        )
        self.assertEqual(response.status_code, 302)
        qtaker = Qtaker.objects.get(email="levels@example.com")
        self.assertEqual(qtaker.skill, "beginner")
        self.assertEqual(len(qtaker.current_question_set), 5)

        # Answer all beginner questions correctly
        for qid in qtaker.current_question_set:
            question = Question.objects.get(id=qid)
            correct_option = Options.objects.get(question=question, correct=True)
            response = self.client.post(
                reverse("quiz:question", args=[qtaker.id, qid]),
                {"answer": str(correct_option.id)},
            )
            self.assertEqual(response.status_code, 302)
            response = self.client.get(
                reverse("quiz:answer", args=[qtaker.id, correct_option.id])
            )
            self.assertEqual(response.status_code, 200)

        # Result page should promote to intermediate
        response = self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.skill, "intermediate")
        intermediate_set = qtaker.next_question_set
        self.assertEqual(len(intermediate_set), 5, "Intermediate should have 5 questions")

        # Load first intermediate question (triggers promotion)
        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, intermediate_set[0]])
        )
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.current_question_set, intermediate_set)
        self.assertEqual(qtaker.next_question_set, [])

        # Answer all intermediate questions correctly
        for qid in intermediate_set:
            question = Question.objects.get(id=qid)
            correct_option = Options.objects.get(question=question, correct=True)
            response = self.client.post(
                reverse("quiz:question", args=[qtaker.id, qid]),
                {"answer": str(correct_option.id)},
            )
            self.assertEqual(response.status_code, 302)
            response = self.client.get(
                reverse("quiz:answer", args=[qtaker.id, correct_option.id])
            )
            self.assertEqual(response.status_code, 200)

        # Result page should promote to expert
        response = self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.skill, "expert")
        expert_set = qtaker.next_question_set
        self.assertEqual(len(expert_set), 5, "Expert should have 5 questions")

        # Load first expert question (triggers promotion)
        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, expert_set[0]])
        )
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.current_question_set, expert_set)
        self.assertEqual(qtaker.next_question_set, [])


class QuizFixtureFlowTests(TestCase):
    fixtures = ["quiz/fixtures/initial_quiz.json"]

    def test_fixture_has_five_questions_per_session(self):
        """Ensure each level built from the fixture produces 5-question sessions."""
        response = self.client.post(
            reverse("quiz:register"),
            {"name": "Fixture Tester", "age": 12, "email": "fixture@example.com", "skill": "beginner"},
        )
        self.assertEqual(response.status_code, 302)
        qtaker = Qtaker.objects.get(email="fixture@example.com")
        self.assertEqual(len(qtaker.current_question_set), 5)

        # Answer all beginner questions correctly
        for qid in qtaker.current_question_set:
            question = Question.objects.get(id=qid)
            if question.question_type == "radio":
                correct_option = Options.objects.filter(question=question, correct=True).first()
                answer_value = str(correct_option.id)
                answer_id = correct_option.id
            else:
                correct_option = Options.objects.filter(question=question, correct=True).first()
                answer_value = correct_option.text
                answer_id = 0
            self.client.post(
                reverse("quiz:question", args=[qtaker.id, qid]),
                {"answer": answer_value},
            )
            self.client.get(reverse("quiz:answer", args=[qtaker.id, answer_id]))

        response = self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.skill, "intermediate")
        self.assertEqual(len(qtaker.next_question_set), 5, "Intermediate fixture session should have 5 questions")

        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, qtaker.next_question_set[0]])
        )
        self.assertEqual(response.status_code, 200)

        for qid in qtaker.next_question_set:
            question = Question.objects.get(id=qid)
            if question.question_type == "radio":
                correct_option = Options.objects.filter(question=question, correct=True).first()
                answer_value = str(correct_option.id)
                answer_id = correct_option.id
            else:
                correct_option = Options.objects.filter(question=question, correct=True).first()
                answer_value = correct_option.text
                answer_id = 0
            self.client.post(
                reverse("quiz:question", args=[qtaker.id, qid]),
                {"answer": answer_value},
            )
            self.client.get(reverse("quiz:answer", args=[qtaker.id, answer_id]))

        response = self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertEqual(response.status_code, 200)
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.skill, "expert")
        self.assertEqual(len(qtaker.next_question_set), 5, "Expert fixture session should have 5 questions")

        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, qtaker.next_question_set[0]])
        )
        self.assertEqual(response.status_code, 200)


class CoachQuestionSubmissionTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", password="testpass", email="coach@example.com"
        )
        self.coach.is_coach = True
        self.coach.save()
        self.student = User.objects.create_user(
            username="student", password="testpass", email="student@example.com"
        )
        self.questionnaire = Questionnaire.objects.create(
            title="beginner", description="Beginner level quiz", created_by=self.coach
        )

    def _radio_post_data(self, **overrides):
        data = {
            "questionnaire": self.questionnaire.id,
            "question_type": "radio",
            "question": "Which piece moves in an L shape?",
            "option_1": "Rook",
            "option_2": "Knight",
            "option_3": "Bishop",
            "option_4": "",
            "correct_option": "2",
        }
        data.update(overrides)
        return data

    def test_submit_page_requires_login(self):
        response = self.client.get(reverse("quiz:submit_question"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_coach_can_submit_radio_question(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("quiz:submit_question"), self._radio_post_data()
        )
        self.assertRedirects(
            response, reverse("scheduling:coach_dashboard"), fetch_redirect_response=False
        )
        question = Question.objects.get(created_by=self.coach)
        self.assertFalse(question.is_approved)
        self.assertEqual(question.placement, 1)
        options = Options.objects.filter(question=question)
        self.assertEqual(options.count(), 3)
        correct = options.get(correct=True)
        self.assertEqual(correct.text, "Knight")

    def test_coach_can_submit_text_question(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("quiz:submit_question"),
            {
                "questionnaire": self.questionnaire.id,
                "question_type": "text",
                "question": "Name the piece that can castle.",
                "expected_answer": "  King  ",
            },
        )
        self.assertRedirects(
            response, reverse("scheduling:coach_dashboard"), fetch_redirect_response=False
        )
        question = Question.objects.get(created_by=self.coach)
        self.assertFalse(question.is_approved)
        option = Options.objects.get(question=question)
        self.assertTrue(option.correct)
        self.assertEqual(option.text, "King")

    def test_submission_gets_next_placement(self):
        Question.objects.create(
            questionnaire=self.questionnaire,
            question="Existing question",
            question_type="radio",
            placement=7,
            created_by=self.coach,
            is_approved=True,
        )
        self.client.force_login(self.coach)
        self.client.post(reverse("quiz:submit_question"), self._radio_post_data())
        question = Question.objects.exclude(placement=7).get()
        self.assertEqual(question.placement, 8)

    def test_student_cannot_submit(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("quiz:submit_question"))
        self.assertRedirects(
            response, reverse("accounts:dashboard"), fetch_redirect_response=False
        )
        response = self.client.post(
            reverse("quiz:submit_question"), self._radio_post_data()
        )
        self.assertRedirects(
            response, reverse("accounts:dashboard"), fetch_redirect_response=False
        )
        self.assertEqual(Question.objects.count(), 0)

    def test_radio_requires_correct_option(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("quiz:submit_question"),
            self._radio_post_data(correct_option=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Question.objects.count(), 0)

    def test_radio_correct_option_must_be_filled(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("quiz:submit_question"),
            self._radio_post_data(correct_option="4"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Question.objects.count(), 0)

    def test_radio_requires_two_options(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("quiz:submit_question"),
            self._radio_post_data(option_2="", option_3="", correct_option="1"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Question.objects.count(), 0)

    def test_text_requires_expected_answer(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("quiz:submit_question"),
            {
                "questionnaire": self.questionnaire.id,
                "question_type": "text",
                "question": "Name the piece that can castle.",
                "expected_answer": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Question.objects.count(), 0)

    def test_unapproved_questions_not_served_until_approved(self):
        question = Question.objects.create(
            questionnaire=self.questionnaire,
            question="Pending question",
            question_type="radio",
            placement=1,
            created_by=self.coach,
            is_approved=False,
        )
        qtaker = Qtaker.objects.create(
            name="Taker", age=10, email="taker@example.com", skill="beginner"
        )
        self.assertIsNone(_build_session(qtaker, self.questionnaire))

        question.is_approved = True
        question.save()
        session = _build_session(qtaker, self.questionnaire)
        self.assertIn(question.id, session)


class MotifQuizTests(TestCase):
    """Motif-specific quiz sessions (quiz:motif_quiz)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="motifuser", password="testpass", email="motif@example.com"
        )
        self.pins_easy = Questionnaire.objects.create(
            title="Pins — Easy",
            description="Pin puzzles",
            motif="pins",
            difficulty="easy",
            created_by=self.user,
        )
        self.pins_question = Question.objects.create(
            questionnaire=self.pins_easy,
            question="White to play — pins.",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        Options.objects.create(question=self.pins_question, text="Bd5", correct=True)
        # A question in a *different* questionnaire must never leak into the session.
        self.other_questionnaire = Questionnaire.objects.create(
            title="beginner", description="Legacy", created_by=self.user
        )
        Question.objects.create(
            questionnaire=self.other_questionnaire,
            question="Trivia",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )

    def test_requires_login(self):
        response = self.client.get(reverse("quiz:motif_quiz", args=["pins", "easy"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_builds_session_from_matching_questionnaire_only(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("quiz:motif_quiz", args=["pins", "easy"]))
        self.assertEqual(response.status_code, 302)
        qtaker = Qtaker.objects.get(user=self.user)
        self.assertEqual(qtaker.current_question_set, [self.pins_question.id])
        self.assertRedirects(
            response,
            reverse("quiz:question", args=[qtaker.id, self.pins_question.id]),
            fetch_redirect_response=False,
        )

    def test_question_page_works_with_non_skill_questionnaire_title(self):
        """Regression: questionnaire titled 'Pins — Easy' must not 404 the flow."""
        self.client.force_login(self.user)
        self.client.get(reverse("quiz:motif_quiz", args=["pins", "easy"]))
        qtaker = Qtaker.objects.get(user=self.user)
        response = self.client.get(
            reverse("quiz:question", args=[qtaker.id, self.pins_question.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "quiz/question.html")

    def test_unknown_motif_redirects_with_message(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("quiz:motif_quiz", args=["forks", "hard"]))
        self.assertRedirects(
            response, reverse("quiz:register"), fetch_redirect_response=False
        )
        self.assertFalse(Qtaker.objects.filter(user=self.user).exists())

    def test_questionnaire_without_approved_questions_redirects(self):
        self.pins_question.is_approved = False
        self.pins_question.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("quiz:motif_quiz", args=["pins", "easy"]))
        self.assertRedirects(
            response, reverse("quiz:register"), fetch_redirect_response=False
        )


class QuestionResultTests(TestCase):
    """Per-question outcome recording in quiz_answer_view."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="qr", password="testpass", email="qr@example.com"
        )
        self.questionnaire = Questionnaire.objects.create(
            title="beginner", description="Legacy", created_by=self.user
        )
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question="Most powerful piece?",
            question_type="radio",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        self.correct = Options.objects.create(question=self.question, text="Queen", correct=True)
        self.wrong = Options.objects.create(question=self.question, text="Pawn", correct=False)

    def _answer(self, option):
        qtaker = Qtaker.objects.create(name="QR", email="qr@example.com", user=self.user)
        qtaker.current_question_set = [self.question.id]
        qtaker.save()
        self.client.force_login(self.user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, self.question.id]),
            {"answer": str(option.id)},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, option.id]))
        return qtaker

    def test_correct_answer_recorded(self):
        qtaker = self._answer(self.correct)
        result = Qtaker.objects.get(id=qtaker.id).questionresult_set.get()
        self.assertTrue(result.correct)
        self.assertEqual(result.answer_given, "Queen")
        self.assertEqual(result.question, self.question)

    def test_wrong_answer_recorded_as_incorrect(self):
        qtaker = self._answer(self.wrong)
        result = qtaker.questionresult_set.get()
        self.assertFalse(result.correct)

    def test_revisiting_answer_page_does_not_duplicate(self):
        qtaker = self._answer(self.correct)
        self.client.get(reverse("quiz:answer", args=[qtaker.id, self.correct.id]))
        self.assertEqual(qtaker.questionresult_set.count(), 1)


class BadgeTests(TestCase):
    """Badge awarding on passed motif quizzes."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="badger", password="testpass", email="badger@example.com"
        )
        self.pins_easy = Questionnaire.objects.create(
            title="Pins — Easy",
            description="Pin puzzles",
            motif="pins",
            difficulty="easy",
            created_by=self.user,
        )
        self.question = Question.objects.create(
            questionnaire=self.pins_easy,
            question="White to play — pins.",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        Options.objects.create(question=self.question, text="Bd5", correct=True)
        Options.objects.create(question=self.question, text="Bc4", correct=False)

    def _complete_quiz(self, answers_correct):
        qtaker = Qtaker.objects.create(name="Badger", email="badger@example.com", user=self.user)
        qtaker.current_question_set = [self.question.id]
        qtaker.save()
        self.client.force_login(self.user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, self.question.id]),
            {"answer": "Bd5" if answers_correct else "wrong"},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.client.get(reverse("quiz:result", args=[qtaker.id]))
        qtaker.refresh_from_db()
        return qtaker

    def test_passing_motif_quiz_awards_badge(self):
        self._complete_quiz(answers_correct=True)
        badge = Badge.objects.get(slug="motif-pins-easy")
        self.assertEqual(badge.motif, "pins")
        self.assertEqual(badge.difficulty, "easy")
        self.assertTrue(
            UserBadge.objects.filter(user=self.user, badge=badge).exists()
        )

    def test_failing_quiz_awards_no_badge(self):
        self._complete_quiz(answers_correct=False)
        self.assertFalse(UserBadge.objects.filter(user=self.user).exists())

    def test_retake_does_not_duplicate_badge(self):
        self._complete_quiz(answers_correct=True)
        self._complete_quiz(answers_correct=True)
        badge = Badge.objects.get(slug="motif-pins-easy")
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge=badge).count(), 1
        )

    def test_legacy_quiz_awards_no_badge(self):
        legacy = Questionnaire.objects.create(
            title="beginner", description="Legacy", created_by=self.user
        )
        question = Question.objects.create(
            questionnaire=legacy,
            question="Trivia",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        Options.objects.create(question=question, text="Yes", correct=True)
        qtaker = Qtaker.objects.create(name="Badger", email="badger@example.com", user=self.user)
        qtaker.current_question_set = [question.id]
        qtaker.save()
        self.client.force_login(self.user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, question.id]), {"answer": "Yes"}
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.client.get(reverse("quiz:result", args=[qtaker.id]))
        self.assertFalse(UserBadge.objects.filter(user=self.user).exists())


class ProficiencyTests(TestCase):
    """get_proficiency aggregation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="prof", password="testpass", email="prof@example.com"
        )

    def _make_session(self, motif, difficulty, test_result):
        questionnaire = Questionnaire.objects.create(
            title=f"{motif}-{difficulty}-{test_result}",
            description="",
            motif=motif,
            difficulty=difficulty,
            created_by=self.user,
        )
        question = Question.objects.create(
            questionnaire=questionnaire,
            question="Q",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        qtaker = Qtaker.objects.create(
            name="Prof",
            email="prof@example.com",
            user=self.user,
            test_result=test_result,
        )
        QuestionResult.objects.create(
            qtaker=qtaker, question=question, correct=True, answer_given="x"
        )
        return qtaker

    def test_new_user_has_all_motifs_at_zero(self):
        proficiency = get_proficiency(self.user)
        self.assertEqual(len(proficiency), len(Questionnaire.QUESTION_MOTIFS))
        self.assertTrue(all(entry["level_value"] == 0 for entry in proficiency))

    def test_passed_easy_sets_level(self):
        self._make_session("pins", "easy", 80.0)
        entry = next(e for e in get_proficiency(self.user) if e["motif"] == "pins")
        self.assertEqual(entry["level"], "easy")
        self.assertEqual(entry["level_value"], 1)
        self.assertEqual(entry["attempts"], 1)
        self.assertEqual(entry["best_score"], 80.0)

    def test_highest_passed_difficulty_wins(self):
        self._make_session("pins", "easy", 100.0)
        self._make_session("pins", "hard", 70.0)
        entry = next(e for e in get_proficiency(self.user) if e["motif"] == "pins")
        self.assertEqual(entry["level"], "hard")
        self.assertEqual(entry["level_value"], 3)

    def test_failed_attempts_give_no_level(self):
        self._make_session("pins", "easy", 40.0)
        entry = next(e for e in get_proficiency(self.user) if e["motif"] == "pins")
        self.assertIsNone(entry["level"])
        self.assertEqual(entry["level_value"], 0)
        self.assertEqual(entry["attempts"], 1)

    def test_legacy_questionnaire_excluded(self):
        legacy = Questionnaire.objects.create(
            title="beginner", description="Legacy", created_by=self.user
        )
        question = Question.objects.create(
            questionnaire=legacy,
            question="Trivia",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
        )
        qtaker = Qtaker.objects.create(
            name="Prof", email="prof@example.com", user=self.user, test_result=100.0
        )
        QuestionResult.objects.create(qtaker=qtaker, question=question, correct=True)
        proficiency = get_proficiency(self.user)
        self.assertTrue(all(entry["attempts"] == 0 for entry in proficiency))


class BoardGradingTests(TestCase):
    """Interactive board answers graded against Question.solution_uci."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="board", password="testpass", email="board@example.com"
        )
        self.questionnaire = Questionnaire.objects.create(
            title="Mate in 1 — Easy",
            description="",
            motif="mate_in_1",
            difficulty="easy",
            created_by=self.user,
        )
        # Back-rank mate: Ra8#. Deliberately NO Options rows — grading must
        # come from solution_uci alone.
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question="White to play — mate in 1.",
            question_type="text",
            placement=1,
            created_by=self.user,
            is_approved=True,
            fen="6k1/5ppp/8/8/8/8/8/R6K w - - 0 1",
            solution_uci="a1a8",
        )

    def _play(self, move):
        qtaker = Qtaker.objects.create(name="B", email="board@example.com", user=self.user)
        qtaker.current_question_set = [self.question.id]
        qtaker.save()
        self.client.force_login(self.user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, self.question.id]),
            {"answer": move},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        qtaker.refresh_from_db()
        return qtaker

    def test_correct_uci_move_scores(self):
        qtaker = self._play("a1a8")
        self.assertEqual(qtaker.current_score, 1)
        self.assertTrue(qtaker.questionresult_set.get().correct)

    def test_wrong_move_does_not_score(self):
        qtaker = self._play("a1a7")
        self.assertEqual(qtaker.current_score, 0)
        self.assertFalse(qtaker.questionresult_set.get().correct)

    def test_move_is_case_insensitive_and_trimmed(self):
        qtaker = self._play("  A1A8 ")
        self.assertEqual(qtaker.current_score, 1)


class MotifProgressionTests(TestCase):
    """Passing a motif quiz should offer the same motif at the next difficulty,
    without touching qtaker.skill (legacy skill progression stays legacy)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="prog", password="testpass", email="prog@example.com"
        )
        self.pins_easy = Questionnaire.objects.create(
            title="Pins — Easy", description="", motif="pins",
            difficulty="easy", created_by=self.user,
        )
        self.easy_question = Question.objects.create(
            questionnaire=self.pins_easy, question="Easy pin", question_type="text",
            placement=1, created_by=self.user, is_approved=True,
        )
        Options.objects.create(question=self.easy_question, text="Bd5", correct=True)
        self.pins_medium = Questionnaire.objects.create(
            title="Pins — Medium", description="", motif="pins",
            difficulty="medium", created_by=self.user,
        )
        self.medium_question = Question.objects.create(
            questionnaire=self.pins_medium, question="Medium pin", question_type="text",
            placement=1, created_by=self.user, is_approved=True,
        )
        Options.objects.create(question=self.medium_question, text="Qd1", correct=True)

    def _pass_quiz(self, questionnaire, question):
        qtaker = Qtaker.objects.create(name="P", email="prog@example.com", user=self.user)
        qtaker.current_question_set = [question.id]
        qtaker.save()
        self.client.force_login(self.user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, question.id]),
            {"answer": Options.objects.get(question=question, correct=True).text},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.client.get(reverse("quiz:result", args=[qtaker.id]))
        qtaker.refresh_from_db()
        return qtaker

    def test_passing_easy_offers_medium_same_motif(self):
        qtaker = self._pass_quiz(self.pins_easy, self.easy_question)
        self.assertEqual(qtaker.next_question_set, [self.medium_question.id])
        self.assertEqual(qtaker.current_question_set, [])
        self.assertEqual(qtaker.skill, "beginner")  # untouched by motif progression

    def test_passing_hard_offers_nothing(self):
        pins_hard = Questionnaire.objects.create(
            title="Pins — Hard", description="", motif="pins",
            difficulty="hard", created_by=self.user,
        )
        hard_question = Question.objects.create(
            questionnaire=pins_hard, question="Hard pin", question_type="text",
            placement=1, created_by=self.user, is_approved=True,
        )
        Options.objects.create(question=hard_question, text="Rh8", correct=True)
        qtaker = self._pass_quiz(pins_hard, hard_question)
        self.assertEqual(qtaker.next_question_set, [])

    def test_passing_medium_after_easy_offers_hard(self):
        """Regression: results accumulate on the qtaker across sessions, so the
        session questionnaire must be derived from the current session only —
        not from the first result ever recorded (the easy session)."""
        pins_hard = Questionnaire.objects.create(
            title="Pins — Hard", description="", motif="pins",
            difficulty="hard", created_by=self.user,
        )
        hard_question = Question.objects.create(
            questionnaire=pins_hard, question="Hard pin", question_type="text",
            placement=1, created_by=self.user, is_approved=True,
        )
        Options.objects.create(question=hard_question, text="Rh8", correct=True)

        # Pass easy — the result page queues medium on this same qtaker.
        qtaker = self._pass_quiz(self.pins_easy, self.easy_question)
        self.assertEqual(qtaker.next_question_set, [self.medium_question.id])

        # Take the queued medium session on the SAME qtaker and pass it.
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, self.medium_question.id]),
            {"answer": Options.objects.get(question=self.medium_question, correct=True).text},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.client.get(reverse("quiz:result", args=[qtaker.id]))
        qtaker.refresh_from_db()
        self.assertEqual(qtaker.next_question_set, [hard_question.id])


class FeedTests(TestCase):
    """Activity feed: badge awards + first-time level-ups."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="feeder", password="testpass", email="feeder@example.com"
        )
        self.questionnaire = Questionnaire.objects.create(
            title="Pins — Easy", description="", motif="pins", difficulty="easy",
            created_by=self.user,
        )
        self.question = Question.objects.create(
            questionnaire=self.questionnaire, question="Easy pin", question_type="text",
            placement=1, created_by=self.user, is_approved=True,
        )
        Options.objects.create(question=self.question, text="Bd5", correct=True)

    def _pass(self):
        qtaker = Qtaker.objects.create(name="P", email="feeder@example.com", user=self.user)
        qtaker.current_question_set = [self.question.id]
        qtaker.save()
        self.client.force_login(self.user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, self.question.id]),
            {"answer": "Bd5"},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.client.get(reverse("quiz:result", args=[qtaker.id]))

    def test_first_pass_writes_badge_and_level_up(self):
        self._pass()
        self.assertEqual(
            sorted(Activity.objects.values_list("kind", flat=True)), ["badge", "level_up"]
        )

    def test_retake_writes_no_new_events(self):
        self._pass()
        self._pass()
        self.assertEqual(Activity.objects.count(), 2)

    def test_level_up_only_on_first_pass_of_pair(self):
        self._pass()
        self._pass()
        level_ups = Activity.objects.filter(kind="level_up")
        self.assertEqual(level_ups.count(), 1)
        self.assertIn("first time", level_ups.get().text)

    def test_feed_requires_login(self):
        response = self.client.get(reverse("quiz:feed"))
        self.assertEqual(response.status_code, 302)

    def test_feed_shows_username_and_text(self):
        self._pass()
        self.client.force_login(self.user)
        response = self.client.get(reverse("quiz:feed"))
        self.assertContains(response, "feeder")
        self.assertContains(response, "earned the")
        self.assertContains(response, "first time")


class LeaderboardTests(TestCase):
    """Per-motif leaderboard: level desc, then best score, then fewest attempts."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="lb-creator", password="testpass", email="lbc@example.com"
        )
        self.pins_easy = Questionnaire.objects.create(
            title="Pins — Easy", description="", motif="pins", difficulty="easy",
            created_by=self.creator,
        )
        self.easy_question = Question.objects.create(
            questionnaire=self.pins_easy, question="Easy pin", question_type="text",
            placement=1, created_by=self.creator, is_approved=True,
        )
        Options.objects.create(question=self.easy_question, text="Bd5", correct=True)
        self.pins_hard = Questionnaire.objects.create(
            title="Pins — Hard", description="", motif="pins", difficulty="hard",
            created_by=self.creator,
        )
        self.hard_question = Question.objects.create(
            questionnaire=self.pins_hard, question="Hard pin", question_type="text",
            placement=1, created_by=self.creator, is_approved=True,
        )
        Options.objects.create(question=self.hard_question, text="Rh8", correct=True)

    def _pass(self, user, questionnaire, question):
        qtaker = Qtaker.objects.create(
            name=user.username, email=user.email, user=user
        )
        qtaker.current_question_set = [question.id]
        qtaker.save()
        self.client.force_login(user)
        self.client.post(
            reverse("quiz:question", args=[qtaker.id, question.id]),
            {"answer": Options.objects.get(question=question, correct=True).text},
        )
        self.client.get(reverse("quiz:answer", args=[qtaker.id, 0]))
        self.client.get(reverse("quiz:result", args=[qtaker.id]))

    def test_requires_login(self):
        response = self.client.get(reverse("quiz:leaderboard", args=["pins"]))
        self.assertEqual(response.status_code, 302)

    def test_unknown_motif_404(self):
        user = User.objects.create_user(username="u1", password="testpass", email="u1@x.com")
        self.client.force_login(user)
        response = self.client.get(reverse("quiz:leaderboard", args=["not_a_motif"]))
        self.assertEqual(response.status_code, 404)

    def test_ranked_by_level_then_attempts(self):
        alice = User.objects.create_user(username="alice", password="p", email="a@x.com")
        bob = User.objects.create_user(username="bob", password="p", email="b@x.com")
        carol = User.objects.create_user(username="carol", password="p", email="c@x.com")
        self._pass(alice, self.pins_hard, self.hard_question)
        self._pass(bob, self.pins_easy, self.easy_question)
        self._pass(carol, self.pins_easy, self.easy_question)
        self._pass(carol, self.pins_easy, self.easy_question)  # retake: same score, more attempts

        user = User.objects.create_user(username="viewer", password="p", email="v@x.com")
        self.client.force_login(user)
        response = self.client.get(reverse("quiz:leaderboard", args=["pins"]))
        names = [row["user"].username for row in response.context["rows"]]
        self.assertEqual(names, ["alice", "bob", "carol"])
        rows = {row["user"].username: row for row in response.context["rows"]}
        self.assertEqual(rows["alice"]["level"], "hard")
        self.assertEqual(rows["bob"]["attempts"], 1)
        self.assertEqual(rows["carol"]["attempts"], 2)

    def test_anonymous_attempts_excluded(self):
        anon = Qtaker.objects.create(name="Anon", email="anon@x.com", user=None, test_result=100.0)
        QuestionResult.objects.create(qtaker=anon, question=self.easy_question, correct=True)
        user = User.objects.create_user(username="viewer2", password="p", email="v2@x.com")
        self.client.force_login(user)
        response = self.client.get(reverse("quiz:leaderboard", args=["pins"]))
        self.assertNotContains(response, "Anon")
        self.assertEqual(len(response.context["rows"]), 0)

    def test_leaderboard_index_redirects(self):
        user = User.objects.create_user(username="viewer3", password="p", email="v3@x.com")
        self.client.force_login(user)
        response = self.client.get(reverse("quiz:leaderboard_index"))
        self.assertRedirects(response, reverse("quiz:leaderboard", args=["mate_in_1"]))

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Questionnaire, Question, Options, Qtaker
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

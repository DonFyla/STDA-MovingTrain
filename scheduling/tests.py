import json
from datetime import date, time, timedelta, timezone as dt_timezone
from unittest.mock import patch
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Coach, AvailabilitySlot, CoachBlockedDate, Booking, FlexibleBooking, SessionReminder, SpecialBooking

User = get_user_model()


def _mock_initialize_success(*args, **kwargs):
    return {
        "success": True,
        "authorization_url": "https://checkout.flutterwave.com/test-booking-url",
        "reference": kwargs.get("reference", "BK-TEST"),
        "message": "Transaction initialized",
    }


def _mock_create_payment_plan(*args, **kwargs):
    return {
        "success": True,
        "plan_id": 3807,
        "data": {"id": 3807},
        "message": "Payment plan created",
    }


class CoachDashboardTests(TestCase):
    def setUp(self):
        self.coach_user = User.objects.create_user(
            email="coach@example.com",
            username="coachuser",
            password="testpass123",
            full_name="Coach User",
            is_coach=True,
            is_student=False,
        )
        self.coach = Coach.objects.create(
            user=self.coach_user,
            name="Coach User",
            email="coach@example.com",
            specialization="Advanced Tactics",
        )
        self.student_user = User.objects.create_user(
            email="student@example.com",
            username="studentuser",
            password="testpass123",
        )

    def test_coach_dashboard_requires_login(self):
        response = self.client.get(reverse("scheduling:coach_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_coach_dashboard_rejects_student(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:coach_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:dashboard"))

    def test_coach_dashboard_renders_for_coach(self):
        self.client.force_login(self.coach_user)
        response = self.client.get(reverse("scheduling:coach_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/coach_dashboard.html")
        self.assertContains(response, "Coach User")
        self.assertContains(response, "Advanced Tactics")

    def test_coach_dashboard_creates_missing_profile(self):
        coach_without_profile = User.objects.create_user(
            email="noprofile@example.com",
            username="noprofile",
            password="testpass123",
            full_name="No Profile Coach",
            is_coach=True,
            is_student=False,
        )
        self.assertFalse(Coach.objects.filter(user=coach_without_profile).exists())
        self.client.force_login(coach_without_profile)
        response = self.client.get(reverse("scheduling:coach_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Coach.objects.filter(user=coach_without_profile).exists())
        coach = Coach.objects.get(user=coach_without_profile)
        self.assertEqual(coach.name, "No Profile Coach")

    def test_coach_can_update_profile(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "update_profile",
                "name": "Updated Coach",
                "bio": "New bio",
                "specialization": "Endgames",
                "email": "updated@example.com",
                "rank_title": "FM",
                "hourly_rate": 15000,
                "meeting_link": "https://meet.example.com",
                "photo_url": "https://example.com/photo.jpg",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.coach.refresh_from_db()
        self.assertEqual(self.coach.name, "Updated Coach")
        self.assertEqual(self.coach.bio, "New bio")
        self.assertEqual(self.coach.hourly_rate, 15000)

    def test_coach_can_upload_profile_photo(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        self.client.force_login(self.coach_user)
        image = BytesIO()
        Image.new("RGB", (100, 100), color="red").save(image, format="JPEG")
        image.seek(0)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "update_profile",
                "name": "Updated Coach",
                "photo": SimpleUploadedFile("photo.jpg", image.read(), content_type="image/jpeg"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.coach.refresh_from_db()
        self.assertTrue(self.coach.photo)
        self.assertIn("photo", self.coach.photo.name)

    def test_coach_can_add_and_delete_availability(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "add_availability",
                "day_of_week": 1,
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration": 60,
                "split_into_slots": False,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AvailabilitySlot.objects.filter(coach=self.coach).count(), 1)

        slot = AvailabilitySlot.objects.first()
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "delete_availability",
                "slot_id": str(slot.id),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AvailabilitySlot.objects.filter(coach=self.coach).count(), 0)

    def test_coach_can_bulk_add_availability_slots(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "add_availability",
                "day_of_week": 1,
                "start_time": "09:00",
                "end_time": "12:00",
                "slot_duration": 60,
                "split_into_slots": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        slots = AvailabilitySlot.objects.filter(coach=self.coach).order_by("start_time")
        self.assertEqual(slots.count(), 3)
        self.assertEqual(slots[0].start_time, time(9, 0))
        self.assertEqual(slots[0].end_time, time(10, 0))
        self.assertEqual(slots[1].start_time, time(10, 0))
        self.assertEqual(slots[2].start_time, time(11, 0))

    def test_bulk_availability_skips_exact_duplicates(self):
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "add_availability",
                "day_of_week": 1,
                "start_time": "09:00",
                "end_time": "12:00",
                "slot_duration": 60,
                "split_into_slots": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AvailabilitySlot.objects.filter(coach=self.coach).count(), 3)

    def test_bulk_availability_ignores_partial_range(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "add_availability",
                "day_of_week": 1,
                "start_time": "09:00",
                "end_time": "09:30",
                "slot_duration": 60,
                "split_into_slots": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AvailabilitySlot.objects.filter(coach=self.coach).count(), 0)

    def test_coach_can_add_single_unsplit_availability_slot(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "add_availability",
                "day_of_week": 2,
                "start_time": "09:00",
                "end_time": "14:00",
                "slot_duration": 60,
                "split_into_slots": False,
            },
        )
        self.assertEqual(response.status_code, 302)
        slots = AvailabilitySlot.objects.filter(coach=self.coach)
        self.assertEqual(slots.count(), 1)
        self.assertEqual(slots.first().start_time, time(9, 0))
        self.assertEqual(slots.first().end_time, time(14, 0))

    def test_coach_can_add_and_delete_blocked_date(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "add_blocked_date",
                "blocked_date": "2030-12-25",
                "reason": "Holiday",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CoachBlockedDate.objects.filter(coach=self.coach).count(), 1)

        block = CoachBlockedDate.objects.first()
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {
                "action": "delete_blocked_date",
                "block_id": str(block.id),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CoachBlockedDate.objects.filter(coach=self.coach).count(), 0)

    def test_coach_dashboard_shows_flexible_bookings(self):
        FlexibleBooking.objects.create(
            user=self.student_user,
            coach=self.coach,
            session_date=date(2030, 12, 25),
            start_time=time(11, 0),
            end_time=time(12, 0),
            day_of_week=3,
            points_used=2,
            status="confirmed",
            student_notes="Focus on openings",
        )
        self.client.force_login(self.coach_user)
        response = self.client.get(reverse("scheduling:coach_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Points Bookings")
        self.assertContains(response, "Focus on openings")
        self.assertContains(response, "2 points")


class EffectiveAvailabilityTests(TestCase):
    def setUp(self):
        self.coach_user = User.objects.create_user(
            email="availabilitycoach@example.com",
            username="availabilitycoach",
            password="testpass123",
            full_name="Availability Coach",
            is_coach=True,
            is_student=False,
        )
        self.coach = Coach.objects.create(
            user=self.coach_user,
            name="Availability Coach",
            email="availabilitycoach@example.com",
        )

    def test_weekly_slot_without_blocks(self):
        monday = date(2030, 12, 23)  # Monday
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        slots = self.coach.get_available_slots_for_date(monday)
        self.assertEqual(slots, [(time(11, 0), time(12, 0))])

    def test_weekly_slot_partially_blocked(self):
        monday = date(2030, 12, 23)  # Monday
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        CoachBlockedDate.objects.create(
            coach=self.coach,
            blocked_date=monday,
            start_time=time(8, 0),
            end_time=time(13, 0),
        )
        slots = self.coach.get_available_slots_for_date(monday)
        self.assertEqual(slots, [(time(13, 0), time(17, 0))])

    def test_weekly_slot_fully_blocked_by_time_range(self):
        monday = date(2030, 12, 23)  # Monday
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        CoachBlockedDate.objects.create(
            coach=self.coach,
            blocked_date=monday,
            start_time=time(10, 0),
            end_time=time(13, 0),
        )
        slots = self.coach.get_available_slots_for_date(monday)
        self.assertEqual(slots, [])

    def test_weekly_slot_blocked_by_full_day(self):
        monday = date(2030, 12, 23)  # Monday
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        CoachBlockedDate.objects.create(
            coach=self.coach,
            blocked_date=monday,
        )
        slots = self.coach.get_available_slots_for_date(monday)
        self.assertEqual(slots, [])

    def test_block_splits_slot_into_two(self):
        monday = date(2030, 12, 23)  # Monday
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        CoachBlockedDate.objects.create(
            coach=self.coach,
            blocked_date=monday,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        slots = self.coach.get_available_slots_for_date(monday)
        self.assertEqual(slots, [
            (time(9, 0), time(11, 0)),
            (time(12, 0), time(17, 0)),
        ])

    def test_unrelated_blocked_date_ignored(self):
        monday = date(2030, 12, 23)  # Monday
        tuesday = date(2030, 12, 24)  # Tuesday
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        CoachBlockedDate.objects.create(
            coach=self.coach,
            blocked_date=tuesday,
            start_time=time(8, 0),
            end_time=time(13, 0),
        )
        slots = self.coach.get_available_slots_for_date(monday)
        self.assertEqual(slots, [(time(11, 0), time(12, 0))])


class BookingFlowTests(TestCase):
    def setUp(self):
        self.coach_user = User.objects.create_user(
            email="bookingcoach@example.com",
            username="bookingcoach",
            password="testpass123",
            full_name="Booking Coach",
            is_coach=True,
            is_student=False,
        )
        self.coach = Coach.objects.create(
            user=self.coach_user,
            name="Booking Coach",
            email="bookingcoach@example.com",
            hourly_rate=10000,
        )
        self.student_user = User.objects.create_user(
            email="bookingstudent@example.com",
            username="bookingstudent",
            password="testpass123",
            full_name="Booking Student",
            phone="+2348012345678",
        )
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,  # Monday
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=3,  # Wednesday
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        # Freeze time so weekday-based slots always satisfy the 24h booking notice
        now_patcher = patch(
            "django.utils.timezone.now",
            return_value=timezone.datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc),
        )
        now_patcher.start()
        self.addCleanup(now_patcher.stop)

    def test_booking_page_requires_login(self):
        response = self.client.get(reverse("scheduling:book_coach", args=[self.coach.id]))
        self.assertEqual(response.status_code, 302)

    def test_booking_page_renders(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.coach.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/book_coach.html")
        self.assertContains(response, self.coach.name)

    @patch("scheduling.views.create_payment_plan", side_effect=_mock_create_payment_plan)
    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_student_can_submit_single_weekly_booking(self, mock_init, mock_plan):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_mode": "single",
                "day_of_week_1": "1",
                "time_slot_1": "11:00|12:00",
                "student_name": "Booking Student",
                "student_email": "bookingstudent@example.com",
                "student_phone": "+2348012345678",
                "course_type": "beginner",
                "notes": "Looking forward to it",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/booking_payment.html")
        self.assertContains(response, "https://checkout.flutterwave.com/test-booking-url")
        self.assertEqual(Booking.objects.count(), 1)
        booking = Booking.objects.first()
        self.assertEqual(booking.coach, self.coach)
        self.assertEqual(booking.student_name, "Booking Student")
        self.assertEqual(booking.booking_mode, "single")
        self.assertEqual(booking.sessions_per_month, 4)
        self.assertEqual(booking.monthly_amount, 40000)
        self.assertEqual(booking.recurring_days, [1])
        self.assertEqual(len(booking.recurring_dates), 4)
        self.assertEqual(booking.payment_status, "pending")
        self.assertTrue(booking.payment_reference.startswith("BK-"))
        self.assertEqual(booking.flutterwave_payment_plan_id, "3807")

    @patch("scheduling.views.create_payment_plan", side_effect=_mock_create_payment_plan)
    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_student_can_submit_double_weekly_booking(self, mock_init, mock_plan):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_mode": "double",
                "day_of_week_1": "1",
                "time_slot_1": "11:00|12:00",
                "day_of_week_2": "3",
                "time_slot_2": "14:00|15:00",
                "student_name": "Booking Student",
                "student_email": "bookingstudent@example.com",
                "student_phone": "+2348012345678",
                "course_type": "beginner",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/booking_payment.html")
        booking = Booking.objects.first()
        self.assertEqual(booking.booking_mode, "double")
        self.assertEqual(booking.sessions_per_month, 8)
        self.assertEqual(booking.monthly_amount, 76000)  # 5% discount
        self.assertEqual(booking.flutterwave_payment_plan_id, "3807")
        self.assertEqual(sorted(booking.recurring_days), [1, 3])
        self.assertEqual(len(booking.recurring_dates), 8)

    def test_booking_rejects_same_day_for_double(self):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_mode": "double",
                "day_of_week_1": "1",
                "time_slot_1": "11:00|12:00",
                "day_of_week_2": "1",
                "time_slot_2": "14:00|15:00",
                "student_name": "Booking Student",
                "student_email": "bookingstudent@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)

    def test_booking_confirmation_page(self):
        self.client.force_login(self.student_user)
        booking = Booking.objects.create(
            coach=self.coach,
            student_name="Booking Student",
            student_email="bookingstudent@example.com",
            booking_date=date(2030, 12, 25),
            start_time=time(11, 0),
            end_time=time(12, 0),
            recurring_days=[1],
            recurring_dates=[{"date": "2030-12-25", "start_time": "11:00", "end_time": "12:00"}],
            sessions_per_month=4,
            monthly_amount=40000,
        )
        response = self.client.get(reverse("scheduling:booking_confirmation", args=[booking.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/booking_confirmation.html")
        self.assertContains(response, self.coach.name)

    def test_recurring_slot_shows_as_booked_after_booking(self):
        from datetime import timedelta as _td

        today = date.today()
        days_ahead = 0 - today.weekday()  # next Monday
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = today + _td(days=days_ahead)

        Booking.objects.create(
            coach=self.coach,
            student_name="First Student",
            student_email="first@example.com",
            booking_date=next_monday,
            start_time=time(11, 0),
            end_time=time(12, 0),
            recurring_days=[1],
            recurring_dates=[{"date": next_monday.isoformat(), "start_time": "11:00", "end_time": "12:00"}],
            sessions_per_month=4,
            monthly_amount=40000,
            status="pending",
        )

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.coach.id]))
        self.assertEqual(response.status_code, 200)

        booked = json.loads(response.context["booked_slots_recurring_json"])
        self.assertIn("1", booked)
        self.assertEqual(len(booked["1"]), 1)
        self.assertEqual(booked["1"][0]["start"], "11:00")
        self.assertEqual(booked["1"][0]["end"], "12:00")

    def test_double_recurring_slots_block_correct_days(self):
        from datetime import timedelta as _td

        today = date.today()
        monday_offset = 0 - today.weekday()
        if monday_offset <= 0:
            monday_offset += 7
        next_monday = today + _td(days=monday_offset)
        next_wednesday = next_monday + _td(days=2)

        Booking.objects.create(
            coach=self.coach,
            student_name="First Student",
            student_email="first@example.com",
            booking_date=next_monday,
            start_time=time(11, 0),
            end_time=time(12, 0),
            recurring_days=[1, 3],
            recurring_dates=[
                {"date": next_monday.isoformat(), "start_time": "11:00", "end_time": "12:00"},
                {"date": next_wednesday.isoformat(), "start_time": "14:00", "end_time": "15:00"},
            ],
            sessions_per_month=8,
            monthly_amount=76000,
            status="pending",
        )

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.coach.id]))
        booked = json.loads(response.context["booked_slots_recurring_json"])

        self.assertIn("1", booked)
        self.assertEqual(booked["1"], [{"start": "11:00", "end": "12:00"}])
        self.assertIn("3", booked)
        self.assertEqual(booked["3"], [{"start": "14:00", "end": "15:00"}])

    def test_points_calendar_hides_recurring_booked_slots(self):
        from datetime import timedelta as _td

        today = date.today()
        monday_offset = 0 - today.weekday()
        if monday_offset <= 0:
            monday_offset += 7
        next_monday = today + _td(days=monday_offset)

        # The coach only has one slot on Monday, and it's booked by a recurring booking
        Booking.objects.create(
            coach=self.coach,
            student_name="First Student",
            student_email="first@example.com",
            booking_date=next_monday,
            start_time=time(11, 0),
            end_time=time(12, 0),
            recurring_days=[1],
            recurring_dates=[{"date": next_monday.isoformat(), "start_time": "11:00", "end_time": "12:00"}],
            sessions_per_month=4,
            monthly_amount=40000,
            status="pending",
        )

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.coach.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fully Booked")

    @patch("scheduling.views.create_payment_plan", side_effect=_mock_create_payment_plan)
    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_recurring_booking_sends_creation_emails(self, mock_init, mock_plan):
        self.client.force_login(self.student_user)
        self.coach.email = "coach@example.com"
        self.coach.save()
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_mode": "single",
                "day_of_week_1": "1",
                "time_slot_1": "11:00|12:00",
                "student_name": "Booking Student",
                "student_email": "bookingstudent@example.com",
                "student_phone": "+2348012345678",
                "course_type": "beginner",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        subjects = [m.subject for m in mail.outbox]
        self.assertIn("Your Booking is Reserved! Complete Payment to Confirm", subjects)
        self.assertIn("New Booking - Booking Student (Pending Payment)", subjects)


class BookingPaymentTests(TestCase):
    def setUp(self):
        self.coach_user = User.objects.create_user(
            email="paymentcoach@example.com",
            username="paymentcoach",
            password="testpass123",
            full_name="Payment Coach",
            is_coach=True,
            is_student=False,
        )
        self.coach = Coach.objects.create(
            user=self.coach_user,
            name="Payment Coach",
            email="paymentcoach@example.com",
            hourly_rate=10000,
        )
        self.student_user = User.objects.create_user(
            email="paymentstudent@example.com",
            username="paymentstudent",
            password="testpass123",
            full_name="Payment Student",
        )
        self.booking = Booking.objects.create(
            coach=self.coach,
            student_name="Payment Student",
            student_email="paymentstudent@example.com",
            booking_date=date(2030, 12, 25),
            start_time=time(11, 0),
            end_time=time(12, 0),
            recurring_days=[1],
            recurring_dates=[{"date": "2030-12-25", "start_time": "11:00", "end_time": "12:00"}],
            sessions_per_month=4,
            monthly_amount=40000,
            payment_reference="BK-CALLBACK-123",
            payment_status="pending",
            status="pending",
        )

    @patch("payments.views.verify_transaction")
    def test_booking_callback_confirms_booking_on_success(self, mock_verify):
        mock_verify.return_value = {
            "success": True,
            "status": "successful",
            "reference": "BK-CALLBACK-123",
            "amount": 40000,
        }
        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("payments:booking_callback"),
            {"reference": "BK-CALLBACK-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("scheduling:booking_confirmation", args=[self.booking.id]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")
        self.assertEqual(self.booking.payment_status, "paid")
        self.assertIsNotNone(self.booking.payment_date)

    @patch("payments.views.verify_transaction")
    def test_booking_callback_shows_error_on_failure(self, mock_verify):
        mock_verify.return_value = {
            "success": True,
            "status": "failed",
            "reference": "BK-CALLBACK-123",
        }
        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("payments:booking_callback"),
            {"reference": "BK-CALLBACK-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")
        self.assertEqual(self.booking.payment_status, "pending")


class SubscriptionCancellationTests(TestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(
            email="cancelsub@example.com",
            username="cancelsub",
            password="testpass123",
        )
        self.coach = Coach.objects.create(name="Sub Coach", email="subcoach@example.com")
        self.booking = Booking.objects.create(
            coach=self.coach,
            student_name="Cancel Student",
            student_email="cancelsub@example.com",
            booking_date=date(2030, 12, 25),
            start_time=time(11, 0),
            end_time=time(12, 0),
            recurring_days=[1],
            recurring_dates=[{"date": "2030-12-25", "start_time": "11:00", "end_time": "12:00"}],
            sessions_per_month=4,
            monthly_amount=40000,
            flutterwave_payment_plan_id="3807",
            flutterwave_subscription_id="sub_123",
            payment_status="paid",
            status="confirmed",
            subscription_status="active",
        )

    @patch("scheduling.views.cancel_subscription")
    def test_student_can_cancel_subscription(self, mock_cancel):
        mock_cancel.return_value = {"success": True, "message": "Cancelled"}
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:cancel_subscription", args=[self.booking.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.subscription_status, "cancelled")
        self.assertEqual(self.booking.status, "cancelled")


class CoachBookingManagementTests(TestCase):
    def setUp(self):
        self.coach_user = User.objects.create_user(
            email="managecoach@example.com",
            username="managecoach",
            password="testpass123",
            full_name="Manage Coach",
            is_coach=True,
            is_student=False,
        )
        self.coach = Coach.objects.create(
            user=self.coach_user,
            name="Manage Coach",
            email="managecoach@example.com",
        )
        self.booking = Booking.objects.create(
            coach=self.coach,
            student_name="Student",
            student_email="student@example.com",
            booking_date=date(2030, 12, 25),
            start_time=time(11, 0),
            end_time=time(12, 0),
            status="pending",
        )

    def test_coach_can_confirm_paid_booking(self):
        self.booking.payment_status = "paid"
        self.booking.save()
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {"action": "confirm_booking", "booking_id": str(self.booking.id)},
        )
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")

    def test_coach_cannot_confirm_unpaid_booking(self):
        self.assertEqual(self.booking.payment_status, "pending")
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {"action": "confirm_booking", "booking_id": str(self.booking.id)},
        )
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")

    def test_coach_can_reject_booking(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {"action": "reject_booking", "booking_id": str(self.booking.id)},
        )
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "rejected")

    def test_other_coach_cannot_confirm_booking(self):
        other_user = User.objects.create_user(
            email="othercoach@example.com",
            username="othercoach",
            password="testpass123",
            full_name="Other Coach",
            is_coach=True,
            is_student=False,
        )
        Coach.objects.create(user=other_user, name="Other Coach", email="othercoach@example.com")
        self.client.force_login(other_user)
        response = self.client.post(
            reverse("scheduling:coach_dashboard"),
            {"action": "confirm_booking", "booking_id": str(self.booking.id)},
        )
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")


class PointsBookingFlowTests(TestCase):
    def setUp(self):
        self.coach_user = User.objects.create_user(
            email="pointscoach@example.com",
            username="pointscoach",
            password="testpass123",
            full_name="Points Coach",
            is_coach=True,
            is_student=False,
        )
        self.coach = Coach.objects.create(
            user=self.coach_user,
            name="Points Coach",
            email="pointscoach@example.com",
            hourly_rate=10000,
            points_cost=2,
            meeting_link="https://meet.example.com/points",
        )
        self.student_user = User.objects.create_user(
            email="pointsstudent@example.com",
            username="pointsstudent",
            password="testpass123",
            full_name="Points Student",
        )
        from payments.points_service import add_points
        add_points(self.student_user, 10, description="Test top-up", payment_reference="TEST")

        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=3,
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        # Freeze time so weekday-based slots always satisfy the 24h booking notice
        now_patcher = patch(
            "django.utils.timezone.now",
            return_value=timezone.datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc),
        )
        now_patcher.start()
        self.addCleanup(now_patcher.stop)

    def _future_monday(self):
        from datetime import timedelta as _td
        today = date.today()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + _td(days=days_ahead)

    def test_booking_page_has_points_tab(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.coach.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Book with Points")
        self.assertContains(response, "Book Recurring Classes")

    def test_points_booking_creates_flexible_bookings(self):
        from payments.models import UserPoints, PointTransaction
        from scheduling.models import FlexibleBooking

        monday = self._future_monday()
        slots_payload = [
            {
                "date": monday.isoformat(),
                "day_of_week": 1,
                "start_time": "11:00",
                "end_time": "12:00",
            }
        ]

        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_type": "points",
                "selected_slots": json.dumps(slots_payload),
                "student_name": "Points Student",
                "student_email": "pointsstudent@example.com",
                "student_phone": "+2348012345678",
                "student_notes": "Please focus on openings",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FlexibleBooking.objects.count(), 1)
        flex = FlexibleBooking.objects.first()
        self.assertEqual(flex.user, self.student_user)
        self.assertEqual(flex.coach, self.coach)
        self.assertEqual(flex.points_used, 2)
        self.assertEqual(flex.session_date, monday)
        self.assertEqual(flex.start_time, time(11, 0))
        self.assertEqual(flex.end_time, time(12, 0))
        self.assertEqual(flex.status, "confirmed")

        points = UserPoints.objects.get(user=self.student_user)
        self.assertEqual(points.balance, 8)

        tx = PointTransaction.objects.filter(user=self.student_user, type="usage").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, -2)
        self.assertEqual(tx.balance_after, 8)

        self.assertEqual(len(mail.outbox), 2)
        subjects = [m.subject for m in mail.outbox]
        self.assertIn("Your Session Has Been Booked", subjects)
        self.assertIn("New Session Booking - Points Student", subjects)

    def test_points_booking_rejects_insufficient_balance(self):
        from scheduling.models import FlexibleBooking
        from payments.points_service import get_or_create_user_points

        points = get_or_create_user_points(self.student_user)
        points.balance = 1
        points.save()

        monday = self._future_monday()
        slots_payload = [
            {
                "date": monday.isoformat(),
                "day_of_week": 1,
                "start_time": "11:00",
                "end_time": "12:00",
            }
        ]

        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_type": "points",
                "selected_slots": json.dumps(slots_payload),
                "student_name": "Points Student",
                "student_email": "pointsstudent@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FlexibleBooking.objects.count(), 0)

    def test_points_booking_rejects_empty_slots(self):
        from scheduling.models import FlexibleBooking

        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.coach.id]),
            {
                "booking_type": "points",
                "selected_slots": "",
                "student_name": "Points Student",
                "student_email": "pointsstudent@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FlexibleBooking.objects.count(), 0)

    def test_flexible_booking_confirmation_page(self):
        from scheduling.models import FlexibleBooking
        flex = FlexibleBooking.objects.create(
            user=self.student_user,
            coach=self.coach,
            session_date=date(2030, 12, 25),
            start_time=time(11, 0),
            end_time=time(12, 0),
            day_of_week=3,
            points_used=2,
        )
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("scheduling:flexible_booking_confirmation", args=[flex.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/flexible_booking_confirmation.html")
        self.assertContains(response, self.coach.name)


class SpecialBookingFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="student@example.com",
            username="studentuser",
            password="testpass123",
            full_name="Test Student",
        )
        self.special_coach = Coach.objects.create(
            name="Elite Coach",
            email="elite@example.com",
            is_special=True,
            hourly_rate=15000,
        )
        AvailabilitySlot.objects.create(
            coach=self.special_coach,
            day_of_week=2,  # Tuesday
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        AvailabilitySlot.objects.create(
            coach=self.special_coach,
            day_of_week=3,  # Wednesday
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        AvailabilitySlot.objects.create(
            coach=self.special_coach,
            day_of_week=4,  # Thursday
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        self.normal_coach = Coach.objects.create(
            name="Regular Coach",
            email="regular@example.com",
            is_special=False,
        )
        # Freeze time so weekday-based slots always satisfy the 24h booking notice
        now_patcher = patch(
            "django.utils.timezone.now",
            return_value=timezone.datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc),
        )
        now_patcher.start()
        self.addCleanup(now_patcher.stop)

    def test_special_tab_shown_for_special_coach(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.special_coach.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pay to Book")

    def test_special_tab_hidden_for_normal_coach(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("scheduling:book_coach", args=[self.normal_coach.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Pay to Book")

    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_special_booking_creation_redirects_to_payment(self, mock_init):
        self.client.force_login(self.student)
        from scheduling.models import SpecialBooking
        today = timezone.now().date()
        # Find next Tuesday
        days_until_tuesday = (1 - today.weekday()) % 7
        next_tuesday = today + timedelta(days=days_until_tuesday if days_until_tuesday else 7)
        selected_slots = json.dumps([
            {
                "date": next_tuesday.isoformat(),
                "day_of_week": 2,
                "start_time": "14:00",
                "end_time": "15:00",
            }
        ])

        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.special_coach.id]),
            {
                "booking_type": "special",
                "selected_slots": selected_slots,
                "student_name": "Test Student",
                "student_email": "student@example.com",
                "student_phone": "08012345678",
            },
        )

        self.assertEqual(SpecialBooking.objects.count(), 1)
        booking = SpecialBooking.objects.first()
        self.assertEqual(booking.total_sessions, 1)
        self.assertEqual(booking.total_amount, 15000)
        self.assertEqual(booking.status, "pending_payment")
        self.assertEqual(booking.payment_status, "pending")
        self.assertTrue(booking.payment_reference.startswith("SP-"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/special_booking_payment.html")
        self.assertContains(response, "https://checkout.flutterwave.com/test-booking-url")
        self.assertEqual(len(mail.outbox), 2)
        subjects = [m.subject for m in mail.outbox]
        self.assertIn("Your Special Coaching Booking is Reserved! Complete Payment to Confirm", subjects)
        self.assertIn("New Special Booking - Test Student (Pending Payment)", subjects)

    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_special_booking_creation_multiple_sessions(self, mock_init):
        self.client.force_login(self.student)
        from scheduling.models import SpecialBooking
        today = timezone.now().date()
        days_until_tuesday = (1 - today.weekday()) % 7
        next_tuesday = today + timedelta(days=days_until_tuesday if days_until_tuesday else 7)
        next_thursday = next_tuesday + timedelta(days=2)
        selected_slots = json.dumps([
            {
                "date": next_tuesday.isoformat(),
                "day_of_week": 2,
                "start_time": "14:00",
                "end_time": "15:00",
            },
            {
                "date": next_thursday.isoformat(),
                "day_of_week": 4,
                "start_time": "14:00",
                "end_time": "15:00",
            }
        ])

        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.special_coach.id]),
            {
                "booking_type": "special",
                "selected_slots": selected_slots,
                "student_name": "Test Student",
                "student_email": "student@example.com",
                "student_phone": "08012345678",
            },
        )

        self.assertEqual(SpecialBooking.objects.count(), 1)
        booking = SpecialBooking.objects.first()
        self.assertEqual(booking.total_sessions, 2)
        self.assertEqual(booking.total_amount, 30000)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduling/special_booking_payment.html")

    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_special_booking_discount_tier_10_percent(self, mock_init):
        self.client.force_login(self.student)
        from scheduling.models import SpecialBooking
        today = timezone.now().date()
        days_until_tuesday = (1 - today.weekday()) % 7
        next_tuesday = today + timedelta(days=days_until_tuesday if days_until_tuesday else 7)

        # Create 8 individual sessions across 4 weeks on Tuesday and Thursday
        selected_slots = []
        for week in range(4):
            tuesday = next_tuesday + timedelta(weeks=week)
            thursday = tuesday + timedelta(days=2)
            selected_slots.append({
                "date": tuesday.isoformat(),
                "day_of_week": 2,
                "start_time": "14:00",
                "end_time": "15:00",
            })
            selected_slots.append({
                "date": thursday.isoformat(),
                "day_of_week": 4,
                "start_time": "14:00",
                "end_time": "15:00",
            })

        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.special_coach.id]),
            {
                "booking_type": "special",
                "selected_slots": json.dumps(selected_slots),
                "student_name": "Test Student",
                "student_email": "student@example.com",
                "student_phone": "08012345678",
            },
        )

        self.assertEqual(SpecialBooking.objects.count(), 1)
        booking = SpecialBooking.objects.first()
        self.assertEqual(booking.total_sessions, 8)
        # 8 * 15000 = 120000, 10% discount = 108000
        self.assertEqual(booking.total_amount, 108000)
        self.assertEqual(response.status_code, 200)

    @patch("scheduling.views.initialize_transaction", side_effect=_mock_initialize_success)
    def test_special_booking_discount_tier_15_percent(self, mock_init):
        self.client.force_login(self.student)
        from scheduling.models import SpecialBooking
        today = timezone.now().date()
        days_until_tuesday = (1 - today.weekday()) % 7
        next_tuesday = today + timedelta(days=days_until_tuesday if days_until_tuesday else 7)

        # Create 12 individual sessions across 4 weeks on Tuesday, Wednesday, Thursday
        selected_slots = []
        for week in range(4):
            tuesday = next_tuesday + timedelta(weeks=week)
            wednesday = tuesday + timedelta(days=1)
            thursday = tuesday + timedelta(days=2)
            selected_slots.append({
                "date": tuesday.isoformat(),
                "day_of_week": 2,
                "start_time": "14:00",
                "end_time": "15:00",
            })
            selected_slots.append({
                "date": wednesday.isoformat(),
                "day_of_week": 3,
                "start_time": "14:00",
                "end_time": "15:00",
            })
            selected_slots.append({
                "date": thursday.isoformat(),
                "day_of_week": 4,
                "start_time": "14:00",
                "end_time": "15:00",
            })

        response = self.client.post(
            reverse("scheduling:book_coach", args=[self.special_coach.id]),
            {
                "booking_type": "special",
                "selected_slots": json.dumps(selected_slots),
                "student_name": "Test Student",
                "student_email": "student@example.com",
                "student_phone": "08012345678",
            },
        )

        self.assertEqual(SpecialBooking.objects.count(), 1)
        booking = SpecialBooking.objects.first()
        self.assertEqual(booking.total_sessions, 12)
        # 12 * 15000 = 180000, 15% discount = 153000
        self.assertEqual(booking.total_amount, 153000)
        self.assertEqual(response.status_code, 200)


class MinimumBookingNoticeTests(TestCase):
    """All booking flows reject sessions starting less than 24 hours from now."""

    def setUp(self):
        self.coach = Coach.objects.create(
            name="Notice Coach",
            email="notice@example.com",
            hourly_rate=10000,
            points_cost=1,
        )
        AvailabilitySlot.objects.create(
            coach=self.coach,
            day_of_week=2,  # Tuesday
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        # Freeze "now" at Monday 2026-01-05 09:00 UTC (10:00 in Africa/Lagos).
        # The 24h cutoff is therefore Tuesday 2026-01-06 10:00 Lagos time.
        now_patcher = patch(
            "django.utils.timezone.now",
            return_value=timezone.datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc),
        )
        now_patcher.start()
        self.addCleanup(now_patcher.stop)

    def _points_form(self, slots):
        from .forms import PointsBookingForm

        return PointsBookingForm(
            data={
                "selected_slots": json.dumps(slots),
                "student_name": "Notice Student",
                "student_email": "student@example.com",
            },
            coach=self.coach,
        )

    def _special_form(self, slots):
        from .forms import SpecialBookingForm

        return SpecialBookingForm(
            data={
                "selected_slots": json.dumps(slots),
                "student_name": "Notice Student",
                "student_email": "student@example.com",
            },
            coach=self.coach,
        )

    def _recurring_form(self, day_of_week, time_slot):
        from .forms import BookingForm

        return BookingForm(
            data={
                "booking_mode": "single",
                "day_of_week_1": str(day_of_week),
                "time_slot_1": time_slot,
                "student_name": "Notice Student",
                "student_email": "student@example.com",
            }
        )

    def test_points_booking_rejects_slot_within_24_hours(self):
        # Tuesday 09:00 Lagos is 23 hours after the frozen now (Monday 10:00)
        form = self._points_form([
            {"date": "2026-01-06", "day_of_week": 2, "start_time": "09:00", "end_time": "10:00"},
        ])
        self.assertFalse(form.is_valid())
        self.assertIn("24 hours", str(form.errors))

    def test_points_booking_allows_slot_after_24_hours(self):
        form = self._points_form([
            {"date": "2026-01-06", "day_of_week": 2, "start_time": "11:00", "end_time": "12:00"},
        ])
        self.assertTrue(form.is_valid(), form.errors)

    def test_special_booking_rejects_session_within_24_hours(self):
        form = self._special_form([
            {"date": "2026-01-06", "day_of_week": 2, "start_time": "09:00", "end_time": "10:00"},
        ])
        self.assertFalse(form.is_valid())
        self.assertIn("24 hours", str(form.errors))

    def test_special_booking_allows_session_after_24_hours(self):
        form = self._special_form([
            {"date": "2026-01-06", "day_of_week": 2, "start_time": "11:00", "end_time": "12:00"},
        ])
        self.assertTrue(form.is_valid(), form.errors)

    def test_recurring_booking_rejects_first_session_within_24_hours(self):
        # First occurrence of Tuesday is 2026-01-06; 09:00 is under 24h away
        form = self._recurring_form(2, "09:00|10:00")
        self.assertFalse(form.is_valid())
        self.assertIn("24 hours", str(form.errors))

    def test_recurring_booking_allows_first_session_after_24_hours(self):
        form = self._recurring_form(2, "11:00|12:00")
        self.assertTrue(form.is_valid(), form.errors)


class SessionNoteTests(TestCase):
    """Coach session notes: write/read history, coach-only access, handover."""

    def setUp(self):
        self.coach_user = User.objects.create_user(
            username="coach1", password="testpass", email="coach1@x.com", is_coach=True
        )
        self.coach = Coach.objects.create(user=self.coach_user, name="Coach One")
        self.other_coach_user = User.objects.create_user(
            username="coach2", password="testpass", email="coach2@x.com", is_coach=True
        )
        Coach.objects.create(user=self.other_coach_user, name="Coach Two")
        self.student = User.objects.create_user(
            username="student1", password="testpass", email="student1@x.com"
        )

    def _link_student(self):
        FlexibleBooking.objects.create(
            user=self.student,
            coach=self.coach,
            session_date=date(2026, 9, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            day_of_week=1,
            points_used=1,
        )

    def test_coach_can_add_note(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:student_note_detail", args=[self.student.id]),
            {"session_date": "2026-09-01", "content": "Covered pins and knight forks."},
        )
        self.assertRedirects(
            response, reverse("scheduling:student_note_detail", args=[self.student.id])
        )
        note = self.student.session_notes.get()
        self.assertEqual(note.coach, self.coach)
        self.assertEqual(note.content, "Covered pins and knight forks.")

    def test_another_coach_sees_history(self):
        self.client.force_login(self.coach_user)
        self.client.post(
            reverse("scheduling:student_note_detail", args=[self.student.id]),
            {"session_date": "2026-09-01", "content": "First coach note about pins."},
        )
        self.client.force_login(self.other_coach_user)
        response = self.client.get(
            reverse("scheduling:student_note_detail", args=[self.student.id])
        )
        self.assertContains(response, "First coach note about pins.")
        self.assertContains(response, "Coach One")
        self.assertContains(response, "proficiencyChart")

    def test_student_cannot_access_notes(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("scheduling:student_notes"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(
            reverse("scheduling:student_note_detail", args=[self.student.id])
        )
        self.assertEqual(response.status_code, 302)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("scheduling:student_notes"))
        self.assertEqual(response.status_code, 302)

    def test_future_date_rejected(self):
        self.client.force_login(self.coach_user)
        response = self.client.post(
            reverse("scheduling:student_note_detail", args=[self.student.id]),
            {"session_date": "2999-01-01", "content": "From the future."},
        )
        self.assertEqual(self.student.session_notes.count(), 0)
        self.assertContains(response, "future")

    def test_empty_content_rejected(self):
        self.client.force_login(self.coach_user)
        self.client.post(
            reverse("scheduling:student_note_detail", args=[self.student.id]),
            {"session_date": "2026-09-01", "content": ""},
        )
        self.assertEqual(self.student.session_notes.count(), 0)

    def test_student_list_shows_linked_student(self):
        self._link_student()
        self.client.force_login(self.coach_user)
        response = self.client.get(reverse("scheduling:student_notes"))
        self.assertContains(response, "student1")

    def test_student_list_search(self):
        self._link_student()
        self.client.force_login(self.coach_user)
        response = self.client.get(reverse("scheduling:student_notes"), {"q": "nomatch"})
        self.assertNotContains(response, "student1")


class SessionReminderTests(TestCase):
    """1-hour-before email reminders for upcoming sessions."""

    def setUp(self):
        self.coach_user = User.objects.create_user(
            username="rcoach", password="testpass", email="rcoach@x.com", is_coach=True
        )
        self.coach = Coach.objects.create(user=self.coach_user, name="Reminder Coach", email="rcoach@x.com")
        self.student = User.objects.create_user(
            username="rstudent", password="testpass", email="rstudent@x.com"
        )
        self.local_now = timezone.localtime()

    def _flexible(self, start_time, status="confirmed"):
        return FlexibleBooking.objects.create(
            user=self.student,
            coach=self.coach,
            session_date=self.local_now.date(),
            start_time=start_time,
            end_time=time(start_time.hour + 1, start_time.minute) if start_time.hour < 23 else time(23, 59),
            day_of_week=self.local_now.weekday(),
            points_used=1,
            status=status,
        )

    def _in_one_hour(self):
        target = self.local_now + timedelta(hours=1)
        return time(target.hour, target.minute)

    def test_reminder_sent_to_student_and_coach(self):
        self._flexible(self._in_one_hour())
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 2)
        recipients = {msg.to[0] for msg in mail.outbox}
        self.assertEqual(recipients, {"rstudent@x.com", "rcoach@x.com"})
        self.assertTrue(
            SessionReminder.objects.filter(kind="flexible").exists()
        )

    def test_reminder_sent_exactly_once(self):
        self._flexible(self._in_one_hour())
        call_command("send_session_reminders")
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(SessionReminder.objects.count(), 1)

    def test_cancelled_session_not_reminded(self):
        self._flexible(self._in_one_hour(), status="cancelled")
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(SessionReminder.objects.count(), 0)

    def test_outside_window_not_reminded(self):
        soon = self.local_now + timedelta(minutes=30)
        self._flexible(time(soon.hour, soon.minute))
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 0)

    def test_recurring_booking_reminded(self):
        Booking.objects.create(
            coach=self.coach,
            student_name=self.student.full_name or self.student.username,
            student_email=self.student.email,
            booking_date=self.local_now.date(),
            start_time=self._in_one_hour(),
            end_time=time(12, 0),
            status="confirmed",
            payment_status="paid",
            recurring_dates=[self.local_now.date().isoformat()],
        )
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(SessionReminder.objects.filter(kind="recurring").exists())

    def test_recurring_unpaid_not_reminded(self):
        Booking.objects.create(
            coach=self.coach,
            student_name=self.student.username,
            student_email=self.student.email,
            booking_date=self.local_now.date(),
            start_time=self._in_one_hour(),
            end_time=time(12, 0),
            status="confirmed",
            payment_status="pending",
            recurring_dates=[self.local_now.date().isoformat()],
        )
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 0)

    def _special(self, start_time, status="confirmed"):
        return SpecialBooking.objects.create(
            coach=self.coach,
            student=self.student,
            student_name=self.student.username,
            student_email=self.student.email,
            total_sessions=1,
            sessions_completed=0,
            session_dates=[{
                "date": self.local_now.date().isoformat(),
                "start_time": start_time.strftime("%H:%M"),
                "end_time": time(start_time.hour + 1, start_time.minute).strftime("%H:%M")
                if start_time.hour < 23 else "23:59",
            }],
            hourly_rate=10000,
            total_amount=10000,
            status=status,
            payment_status="paid",
        )

    def test_special_booking_reminded(self):
        self._special(self._in_one_hour())
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 2)
        reminder = SessionReminder.objects.get(kind="special")
        self.assertEqual(reminder.session_key, self._in_one_hour().strftime("%H:%M"))

    def test_special_booking_reminded_once(self):
        self._special(self._in_one_hour())
        call_command("send_session_reminders")
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(SessionReminder.objects.count(), 1)

    def test_special_pending_payment_not_reminded(self):
        self._special(self._in_one_hour(), status="pending_payment")
        call_command("send_session_reminders")
        self.assertEqual(len(mail.outbox), 0)

    def test_special_two_slots_same_date_both_reminded(self):
        booking = self._special(self._in_one_hour())
        second = self.local_now + timedelta(hours=1, minutes=30)
        if time(second.hour, second.minute) > self._in_one_hour():
            booking.session_dates.append({
                "date": self.local_now.date().isoformat(),
                "start_time": time(second.hour, second.minute).strftime("%H:%M"),
                "end_time": time(second.hour + 1, second.minute).strftime("%H:%M")
                if second.hour < 23 else "23:59",
            })
            booking.total_sessions = 2
            booking.save()
            call_command("send_session_reminders")
            # First slot in window gets reminded now; the second is outside the
            # window and must be picked up on a later run with its own row.
            self.assertEqual(len(mail.outbox), 2)
            self.assertEqual(SessionReminder.objects.count(), 1)

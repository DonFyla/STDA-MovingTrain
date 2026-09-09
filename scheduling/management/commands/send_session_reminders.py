"""Send 1-hour-before email reminders for upcoming sessions.

Run on a schedule (e.g. every 5 minutes). A session is reminded when its start
datetime falls inside a window around the 1-hour-ahead mark; a SessionReminder
row per (booking kind, booking, session date) guarantees exactly-once delivery.

Covered: FlexibleBooking (confirmed), monthly Booking (confirmed + paid, dates from
`recurring_dates`), and SpecialBooking (confirmed, sessions from the `session_dates`
JSONField, each entry {"date", "start_time", "end_time"}). `session_key` in the
SessionReminder rows disambiguates multiple special-booking slots on the same date.
"""

import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from scheduling.emails import send_session_reminder
from scheduling.models import Booking, FlexibleBooking, SessionReminder, SpecialBooking

REMIND_AHEAD = datetime.timedelta(minutes=60)
# Half-window either side of the 1-hour mark — accommodates a scheduler that
# runs every ~5 minutes without reminding twice or missing the window.
WINDOW = datetime.timedelta(minutes=10)


class Command(BaseCommand):
    help = "Send 1-hour-before email reminders for upcoming sessions."

    def handle(self, *args, **options):
        now = timezone.localtime()
        lower = now + REMIND_AHEAD - WINDOW
        upper = now + REMIND_AHEAD + WINDOW
        sent = self._remind_flexible(lower, upper)
        sent += self._remind_recurring(lower, upper)
        sent += self._remind_special(lower, upper)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} session reminder(s)."))

    def _start_in_window(self, session_date, start_time, lower, upper):
        if session_date is None or start_time is None:
            return None
        start_dt = timezone.make_aware(
            datetime.datetime.combine(session_date, start_time)
        )
        return start_dt if lower <= start_dt <= upper else None

    def _mark_reminded(self, kind, booking_id, session_date, session_key=""):
        """Reserve the (kind, booking, date[, slot]) slot. Returns True if we won it."""
        with transaction.atomic():
            _, created = SessionReminder.objects.get_or_create(
                kind=kind, booking_id=booking_id, session_date=session_date,
                session_key=session_key,
            )
            return created

    def _remind_flexible(self, lower, upper):
        count = 0
        bookings = FlexibleBooking.objects.filter(
            status="confirmed",
            session_date__gte=lower.date(),
            session_date__lte=upper.date(),
        ).select_related("user", "coach")
        for booking in bookings:
            if self._start_in_window(booking.session_date, booking.start_time, lower, upper) is None:
                continue
            if not self._mark_reminded("flexible", booking.id, booking.session_date):
                continue
            send_session_reminder(
                student_name=booking.user.full_name or booking.user.username,
                student_email=booking.user.email,
                coach=booking.coach,
                session_date=booking.session_date,
                start_time=booking.start_time,
                end_time=booking.end_time,
                meeting_link=booking.meeting_link or booking.coach.meeting_link or "",
            )
            count += 1
        return count

    def _remind_recurring(self, lower, upper):
        count = 0
        bookings = Booking.objects.filter(
            status="confirmed",
            payment_status="paid",
        ).select_related("coach")
        for booking in bookings:
            for raw_date in booking.recurring_dates or []:
                try:
                    session_date = datetime.date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    continue
                if self._start_in_window(session_date, booking.start_time, lower, upper) is None:
                    continue
                if not self._mark_reminded("recurring", booking.id, session_date):
                    continue
                send_session_reminder(
                    student_name=booking.student_name,
                    student_email=booking.student_email,
                    coach=booking.coach,
                    session_date=session_date,
                    start_time=booking.start_time,
                    end_time=booking.end_time,
                    meeting_link=booking.coach.meeting_link or "",
                )
                count += 1
        return count

    def _remind_special(self, lower, upper):
        # Special bookings store their sessions as a JSONField list of
        # {"date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}.
        count = 0
        bookings = SpecialBooking.objects.filter(status="confirmed").select_related("coach", "student")
        for booking in bookings:
            for session in booking.session_dates or []:
                if not isinstance(session, dict):
                    continue
                try:
                    session_date = datetime.date.fromisoformat(str(session.get("date", ""))[:10])
                    start_time = datetime.datetime.strptime(session["start_time"], "%H:%M").time()
                    end_time = datetime.datetime.strptime(session["end_time"], "%H:%M").time()
                except (KeyError, TypeError, ValueError):
                    continue
                if self._start_in_window(session_date, start_time, lower, upper) is None:
                    continue
                if not self._mark_reminded(
                    "special", booking.id, session_date,
                    session_key=start_time.strftime("%H:%M"),
                ):
                    continue
                send_session_reminder(
                    student_name=booking.student_name,
                    student_email=booking.student_email,
                    coach=booking.coach,
                    session_date=session_date,
                    start_time=start_time,
                    end_time=end_time,
                    meeting_link=booking.coach.meeting_link or "",
                )
                count += 1
        return count

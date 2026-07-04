from datetime import datetime, time
from django.db.models import Q


def is_slot_available(coach, session_date, start_time, end_time, exclude_flexible_id=None, exclude_booking_id=None, exclude_special_id=None):
    """Return True if the requested slot is available for the coach.

    Checks:
    - The slot falls within at least one of the coach's availability slots.
    - The slot is not fully covered by a blocked date/range.
    - The slot does not overlap with existing confirmed bookings.
    """
    from .models import FlexibleBooking, Booking, SpecialBooking

    # Parse inputs if needed.
    if isinstance(session_date, str):
        from datetime import date as dt_date
        session_date = dt_date.fromisoformat(session_date)
    if isinstance(start_time, str):
        start_time = datetime.strptime(start_time, "%H:%M").time()
    if isinstance(end_time, str):
        end_time = datetime.strptime(end_time, "%H:%M").time()

    def to_minutes(t):
        return t.hour * 60 + t.minute

    start_m = to_minutes(start_time)
    end_m = to_minutes(end_time)

    # 1. Must fall within coach availability for that weekday.
    available_slots = coach.get_available_slots_for_date(session_date)
    if not any(
        start_m >= to_minutes(av_start) and end_m <= to_minutes(av_end)
        for av_start, av_end in available_slots
    ):
        return False

    # 2. Must not overlap existing flexible bookings.
    flex_q = FlexibleBooking.objects.filter(
        coach=coach,
        session_date=session_date,
        status="confirmed",
    ).exclude(id=exclude_flexible_id)
    for fb in flex_q:
        fb_start = to_minutes(fb.start_time)
        fb_end = to_minutes(fb.end_time)
        if max(start_m, fb_start) < min(end_m, fb_end):
            return False

    # 3. Must not overlap recurring bookings.
    booking_q = Booking.objects.filter(
        coach=coach,
        status__in=["pending", "confirmed"],
    ).exclude(id=exclude_booking_id)
    for bk in booking_q:
        for slot in bk.recurring_dates or []:
            if slot.get("date") != session_date.isoformat():
                continue
            bk_start = datetime.strptime(slot["start_time"], "%H:%M").time()
            bk_end = datetime.strptime(slot["end_time"], "%H:%M").time()
            bk_start_m = to_minutes(bk_start)
            bk_end_m = to_minutes(bk_end)
            if max(start_m, bk_start_m) < min(end_m, bk_end_m):
                return False

    # 4. Must not overlap special bookings.
    special_q = SpecialBooking.objects.filter(
        coach=coach,
        status__in=["pending_payment", "payment_received", "confirmed"],
    ).exclude(id=exclude_special_id)
    for sb in special_q:
        for slot in sb.session_dates or []:
            if slot.get("date") != session_date.isoformat():
                continue
            sb_start = datetime.strptime(slot["start_time"], "%H:%M").time()
            sb_end = datetime.strptime(slot["end_time"], "%H:%M").time()
            sb_start_m = to_minutes(sb_start)
            sb_end_m = to_minutes(sb_end)
            if max(start_m, sb_start_m) < min(end_m, sb_end_m):
                return False

    return True

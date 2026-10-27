"""Roll forward the class schedule of active recurring subscriptions.

A recurring booking stores its sessions as a static JSON list
(`Booking.recurring_dates`) generated once at signup — 4 weekly occurrences
per booked weekday. Billing, however, is a live monthly Flutterwave
subscription: the renewal webhook advances `next_billing_date` but never
extends the schedule, so subscribers kept paying while their calendars ran
empty after the first month.

`extend_due_subscriptions` is run periodically (see the reminders container)
and appends the next month's sessions to any active subscription whose last
session is within the horizon. It is idempotent: after extending, the last
session sits ~4 weeks out, so it is not re-triggered until the next month.
"""

from datetime import date, timedelta

from django.utils import timezone

from .models import Booking

# Extend when the last stored session is this many days away (or earlier).
HORIZON_DAYS = 7
# How many weekly occurrences to append per booked weekday.
EXTEND_WEEKS = 4


def _parse_session_dates(sessions):
    """Return the valid (date, session) pairs from a recurring_dates list,
    skipping malformed entries."""
    parsed = []
    for s in sessions or []:
        raw = (s or {}).get("date")
        if not raw:
            continue
        try:
            parsed.append((date.fromisoformat(raw), s))
        except ValueError:
            continue
    return parsed


def extend_booking_schedule(booking, weeks=EXTEND_WEEKS):
    """Append `weeks` weekly occurrences per booked weekday, continuing after
    the last stored session of each weekday and preserving its time slot.
    Returns the number of sessions added."""
    existing = list(booking.recurring_dates or [])
    parsed = _parse_session_dates(existing)
    if not parsed:
        return 0

    # Latest occurrence of each weekday carries that day's time slot.
    last_by_weekday = {}
    for d, s in parsed:
        if d.weekday() not in last_by_weekday or d > last_by_weekday[d.weekday()][0]:
            last_by_weekday[d.weekday()] = (d, s)

    new_sessions = []
    for last_date, s in last_by_weekday.values():
        for w in range(1, weeks + 1):
            new_sessions.append({
                "date": (last_date + timedelta(weeks=w)).isoformat(),
                "start_time": s["start_time"],
                "end_time": s["end_time"],
            })

    booking.recurring_dates = existing + new_sessions
    booking.save(update_fields=["recurring_dates"])
    return len(new_sessions)


def extend_due_subscriptions(now=None, horizon_days=HORIZON_DAYS, weeks=EXTEND_WEEKS):
    """Extend the schedule of every active recurring subscription whose last
    session is within `horizon_days` (or already past). Returns how many
    bookings were extended."""
    today = (now or timezone.now()).date()
    horizon = today + timedelta(days=horizon_days)
    extended = 0
    bookings = (
        Booking.objects.filter(subscription_status="active", status="confirmed")
        .exclude(recurring_dates=[])
        .iterator()
    )
    for booking in bookings:
        parsed = _parse_session_dates(booking.recurring_dates)
        if not parsed:
            continue
        if max(d for d, _ in parsed) <= horizon:
            if extend_booking_schedule(booking, weeks):
                extended += 1
    return extended

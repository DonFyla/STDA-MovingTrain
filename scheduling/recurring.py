"""Align recurring class schedules with what subscribers have actually paid for.

A recurring booking stores its sessions as a JSON list
(`Booking.recurring_dates`). Billing is a monthly Flutterwave subscription:
each payment covers one normal block of classes (~4 weekly sessions per
30-day period), tracked by `payment_date` / `next_billing_date`.

The entitlement rule:
- A payment entitles the subscriber to sessions up to
  payment_date + 30 days (the paid window).
- Sessions already past, or inside the paid window, stay — including for
  cancelled subscribers, who keep the classes they paid for.
- Future sessions beyond the paid window are removed: when a renewal is
  declined the window does not advance, so upcoming unpaid classes come
  off the calendar; when a missed renewal is backfilled (or the webhook
  lands), the window extends and the next block is generated.

Runs periodically via the reminders container (reconcile_recurring_schedules
command). Idempotent: only touches schedules that disagree with entitlement.
Bookings that were never paid (pending) are left alone — their dates exist
so the student sees what checkout would buy.
"""

import logging
from datetime import date, timedelta

from django.utils import timezone

from .models import Booking

logger = logging.getLogger(__name__)

# How many days of classes one subscription payment covers; matches the
# webhook's next_billing_date = payment_date + 30 days.
ENTITLEMENT_DAYS = 30


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


def _series_pattern(parsed):
    """Latest occurrence of each weekday carries that day's time slot."""
    pattern = {}
    for d, s in parsed:
        if d.weekday() not in pattern or d > pattern[d.weekday()][0]:
            pattern[d.weekday()] = (d, s["start_time"], s["end_time"])
    return pattern


def align_booking_schedule(booking, entitlement_days=ENTITLEMENT_DAYS):
    """Bring one booking's schedule in line with its paid window.

    Keeps past and paid-for sessions, prunes future sessions beyond the
    paid window, and generates any weekly occurrences missing inside it.
    Returns (added, removed)."""
    if booking.subscription_status not in ("active", "cancelled"):
        return 0, 0
    if booking.payment_date is None:
        return 0, 0
    existing = list(booking.recurring_dates or [])
    parsed = _parse_session_dates(existing)
    if not parsed:
        return 0, 0

    entitlement_end = (booking.payment_date + timedelta(days=entitlement_days)).date()

    kept = [s for d, s in parsed if d < entitlement_end]
    removed = len(parsed) - len(kept)

    added_sessions = []
    for last_date, start, end in _series_pattern(parsed).values():
        d = last_date + timedelta(weeks=1)
        while d < entitlement_end:
            added_sessions.append(
                {"date": d.isoformat(), "start_time": start, "end_time": end}
            )
            d += timedelta(weeks=1)

    if added_sessions or removed:
        kept.extend(added_sessions)
        kept.sort(key=lambda s: s["date"])
        booking.recurring_dates = kept
        booking.save(update_fields=["recurring_dates"])
    return len(added_sessions), removed


def align_due_subscriptions():
    """Align every active or cancelled recurring subscription with its paid
    window. Returns how many bookings changed."""
    aligned = 0
    bookings = Booking.objects.filter(
        subscription_status__in=["active", "cancelled"],
        payment_date__isnull=False,
    ).exclude(recurring_dates=[])
    for booking in bookings.iterator():
        added, removed = align_booking_schedule(booking)
        if added or removed:
            aligned += 1
            if removed:
                logger.warning(
                    "Booking %s schedule aligned to paid window: removed %d "
                    "unpaid session(s), added %d.",
                    booking.id, removed, added,
                )
            else:
                logger.info(
                    "Booking %s schedule extended inside paid window: added %d session(s).",
                    booking.id, added,
                )
    return aligned

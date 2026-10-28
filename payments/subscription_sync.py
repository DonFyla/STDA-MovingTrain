"""Reconcile recurring subscriptions against Flutterwave's API.

The webhook is the real-time path for renewal events, but if it is
misconfigured or a delivery is missed, our DB drifts from reality:
payment_date / next_billing_date freeze, and cancelled subscriptions stay
"active" here (so the class roll-forward keeps generating sessions).

This module pulls the truth from Flutterwave once a day:
- subscription status -> marks cancelled subscriptions in our DB
- recent successful transactions -> backfills missed renewals (billing
  fields + the receipt email the customer never got)

Idempotent: only acts when our state disagrees with Flutterwave's.
"""

import logging
from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from scheduling.models import Booking
from scheduling.emails import send_recurring_payment_received
from .flutterwave_service import list_all_subscriptions, list_all_successful_transactions

logger = logging.getLogger(__name__)

THROTTLE_KEY = "flutterwave_subscription_sync_last_run"
THROTTLE_SECONDS = 23 * 3600  # at most once a day


def _parse_fw_datetime(value):
    """Parse a Flutterwave timestamp (ISO-ish or 'YYYY-MM-DD HH:MM:SS')."""
    if not value:
        return None
    parsed = parse_datetime(str(value).replace(" ", "T", 1))
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _plan_id_of(subscription):
    plan = subscription.get("plan")
    if isinstance(plan, dict):
        return str(plan.get("id") or "")
    return str(plan or "")


def sync_subscriptions(now=None):
    """Pull Flutterwave subscriptions and transactions; bring our DB in line.

    Returns a dict of counters for logging.
    """
    now = now or timezone.now()

    subscriptions, error = list_all_subscriptions()
    if error:
        logger.error("Subscription sync aborted: could not list subscriptions: %s", error)
        return {"status_synced": 0, "billing_synced": 0, "backfilled": 0}

    by_plan = {}
    for sub in subscriptions:
        by_plan.setdefault(_plan_id_of(sub), []).append(sub)

    active_bookings = Booking.objects.filter(
        subscription_status="active",
        flutterwave_payment_plan_id__gt="",
    )
    status_synced = billing_synced = 0
    for booking in active_bookings:
        subs = by_plan.get(booking.flutterwave_payment_plan_id, [])
        # Disambiguate by customer email when several subscriptions share a plan.
        email = (booking.student_email or "").lower()
        matches = [
            s for s in subs
            if (s.get("customer", {}).get("email") or "").lower() == email
        ] or subs
        if not matches:
            logger.info(
                "No Flutterwave subscription found for booking %s (plan %s).",
                booking.id, booking.flutterwave_payment_plan_id,
            )
            continue
        sub = matches[0]

        if sub.get("status") != "active" and booking.status != "cancelled":
            booking.subscription_status = "cancelled"
            booking.status = "cancelled"
            booking.save(update_fields=["subscription_status", "status"])
            status_synced += 1
            logger.warning(
                "Booking %s marked cancelled: Flutterwave subscription %s is %s.",
                booking.id, sub.get("id"), sub.get("status"),
            )

        update_fields = []
        next_payment = _parse_fw_datetime(
            sub.get("next_payment_date") or sub.get("next_due_date")
        )
        if next_payment and (
            booking.next_billing_date is None
            or abs((booking.next_billing_date - next_payment).total_seconds()) > 86400
        ):
            booking.next_billing_date = next_payment
            update_fields.append("next_billing_date")
            billing_synced += 1

        if not booking.flutterwave_subscription_id and sub.get("id"):
            booking.flutterwave_subscription_id = str(sub["id"])
            update_fields.append("flutterwave_subscription_id")

        if update_fields:
            booking.save(update_fields=update_fields)

    # Backfill missed renewals from the recent transaction history.
    window_start = (now - timedelta(days=35)).date().isoformat()
    window_end = now.date().isoformat()
    transactions, error = list_all_successful_transactions(window_start, window_end)
    if error:
        logger.error("Payment backfill aborted: could not list transactions: %s", error)
        return {"status_synced": status_synced, "billing_synced": billing_synced, "backfilled": 0}

    backfilled = 0
    for booking in Booking.objects.filter(
        subscription_status="active",
        flutterwave_payment_plan_id__gt="",
    ):
        email = (booking.student_email or "").lower()
        try:
            expected = Decimal(str(booking.monthly_amount))
        except (InvalidOperation, TypeError):
            continue
        candidates = []
        for tx in transactions:
            if (tx.get("customer", {}).get("email") or "").lower() != email:
                continue
            try:
                if Decimal(str(tx.get("amount"))) != expected:
                    continue
            except (InvalidOperation, TypeError):
                continue
            charged_at = _parse_fw_datetime(tx.get("created_at"))
            if charged_at is None:
                continue
            # Renewals may reuse the first payment's tx_ref, so date is the
            # only reliable way to exclude the already-recorded first payment.
            if booking.payment_date and charged_at <= booking.payment_date:
                continue
            candidates.append((charged_at, tx))
        if not candidates:
            continue
        charged_at, tx = max(candidates, key=lambda c: c[0])
        booking.payment_date = charged_at
        booking.next_billing_date = charged_at + timedelta(days=30)
        booking.save(update_fields=["payment_date", "next_billing_date"])
        backfilled += 1
        logger.warning(
            "Backfilled missed renewal for booking %s from tx %s dated %s.",
            booking.id, tx.get("tx_ref"), charged_at,
        )
        send_recurring_payment_received(booking)

    return {
        "status_synced": status_synced,
        "billing_synced": billing_synced,
        "backfilled": backfilled,
    }


def run_sync(force=False):
    """Throttled entry point: sync at most once per day unless forced."""
    last = cache.get(THROTTLE_KEY)
    now = timezone.now()
    if not force and last:
        last_dt = _parse_fw_datetime(last)
        if last_dt and (now - last_dt).total_seconds() < THROTTLE_SECONDS:
            return None  # too soon
    result = sync_subscriptions(now)
    cache.set(THROTTLE_KEY, now.isoformat(), timeout=None)
    return result

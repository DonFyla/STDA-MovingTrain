import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import PointTransaction
from .flutterwave_service import verify_transaction, verify_webhook_signature


@csrf_exempt
@require_POST
def flutterwave_webhook_view(request):
    """
    Handle Flutterwave webhook events.
    Flutterwave sends a signed POST request with event data.
    """
    secret_key = settings.FLUTTERWAVE_SECRET_KEY
    if not secret_key:
        return JsonResponse(
            {"status": "error", "message": "Flutterwave not configured"},
            status=503,
        )

    # Verify signature
    signature = request.headers.get("verif-hash", "")
    if not verify_webhook_signature(request.body, signature):
        return JsonResponse(
            {"status": "error", "message": "Invalid signature"},
            status=403,
        )

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.completed":
        reference = data.get("tx_ref")
        status = data.get("status")

        if status == "successful" and reference:
            # 1. Try points purchase
            try:
                tx = PointTransaction.objects.get(
                    payment_reference=reference, status="pending"
                )
                from payments.points_service import complete_pending_transaction

                complete_pending_transaction(tx)
                return JsonResponse({"status": "ok"})
            except PointTransaction.DoesNotExist:
                pass

            # 2. Try recurring class booking (one-off or first subscription payment)
            try:
                from scheduling.models import Booking
                from scheduling.emails import (
                    send_recurring_booking_confirmed,
                    send_recurring_payment_received,
                )

                booking = Booking.objects.get(
                    payment_reference=reference, payment_status="pending"
                )

                # Verify amount matches to protect against tampering
                verified = verify_transaction(reference)
                tx_data = verified.get("data", {})
                if verified.get("success") and tx_data.get("status") == "successful":
                    expected_amount = Decimal(str(booking.monthly_amount))
                    actual_amount = Decimal(str(tx_data.get("amount", 0)))
                    if actual_amount == expected_amount:
                        booking.payment_status = "paid"
                        booking.payment_date = timezone.now()
                        booking.status = "confirmed"
                        booking.subscription_status = "active"
                        booking.next_billing_date = timezone.now() + timedelta(days=30)
                        booking.flutterwave_subscription_id = str(
                            tx_data.get("subscription_id") or ""
                        ) or booking.flutterwave_subscription_id
                        booking.save(
                            update_fields=[
                                "payment_status",
                                "payment_date",
                                "status",
                                "subscription_status",
                                "next_billing_date",
                                "flutterwave_subscription_id",
                            ]
                        )
                        send_recurring_booking_confirmed(booking)
                        return JsonResponse({"status": "ok"})
            except Booking.DoesNotExist:
                pass

            # 3. Try recurring subscription renewal (booking already confirmed)
            plan_id = _extract_plan_id(data)
            if plan_id:
                try:
                    from scheduling.models import Booking
                    from scheduling.emails import send_recurring_payment_received

                    booking = Booking.objects.get(
                        flutterwave_payment_plan_id=plan_id,
                        subscription_status="active",
                    )

                    verified = verify_transaction(reference)
                    tx_data = verified.get("data", {})
                    if (
                        verified.get("success")
                        and tx_data.get("status") == "successful"
                    ):
                        expected_amount = Decimal(str(booking.monthly_amount))
                        actual_amount = Decimal(str(tx_data.get("amount", 0)))
                        if actual_amount == expected_amount:
                            booking.payment_date = timezone.now()
                            booking.next_billing_date = timezone.now() + timedelta(
                                days=30
                            )
                            booking.flutterwave_subscription_id = str(
                                tx_data.get("subscription_id") or ""
                            ) or booking.flutterwave_subscription_id
                            booking.save(
                                update_fields=[
                                    "payment_date",
                                    "next_billing_date",
                                    "flutterwave_subscription_id",
                                ]
                            )
                            send_recurring_payment_received(booking)
                            return JsonResponse({"status": "ok"})
                except Booking.DoesNotExist:
                    pass

            # 4. Try special coaching booking
            try:
                from scheduling.models import SpecialBooking

                booking = SpecialBooking.objects.get(
                    payment_reference=reference, payment_status="pending"
                )

                verified = verify_transaction(reference)
                tx_data = verified.get("data", {})
                if verified.get("success") and tx_data.get("status") == "successful":
                    expected_amount = Decimal(str(booking.total_amount))
                    actual_amount = Decimal(str(tx_data.get("amount", 0)))
                    if actual_amount == expected_amount:
                        booking.payment_status = "paid"
                        booking.payment_date = timezone.now()
                        booking.status = "confirmed"
                        booking.save(
                            update_fields=["payment_status", "payment_date", "status"]
                        )
                        return JsonResponse({"status": "ok"})
            except SpecialBooking.DoesNotExist:
                pass

    elif event == "subscription.cancelled":
        plan_info = data.get("plan", {})
        plan_id = str(plan_info.get("id") or "")
        if plan_id:
            try:
                from scheduling.models import Booking
                from scheduling.emails import send_recurring_booking_cancelled

                booking = Booking.objects.get(
                    flutterwave_payment_plan_id=plan_id,
                    subscription_status="active",
                )
                booking.subscription_status = "cancelled"
                booking.status = "cancelled"
                booking.save(update_fields=["subscription_status", "status"])
                send_recurring_booking_cancelled(booking)
                return JsonResponse({"status": "ok"})
            except Booking.DoesNotExist:
                pass

    return JsonResponse({"status": "ok"})


def _extract_plan_id(data):
    """Try to extract the payment plan ID from a webhook payload."""
    for key in ("plan_id", "payment_plan", "payment_plan_id"):
        value = data.get(key)
        if value:
            return str(value)

    # Sometimes nested under a "plan" object.
    plan = data.get("plan", {})
    if plan:
        for key in ("id", "plan_id"):
            value = plan.get(key)
            if value:
                return str(value)
    return None

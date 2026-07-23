import hashlib
import hmac
import json
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

            # 2. Try recurring class booking
            try:
                from scheduling.models import Booking

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
                        booking.save(
                            update_fields=["payment_status", "payment_date", "status"]
                        )
                        return JsonResponse({"status": "ok"})
            except Booking.DoesNotExist:
                pass

            # 3. Try special coaching booking
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

    return JsonResponse({"status": "ok"})

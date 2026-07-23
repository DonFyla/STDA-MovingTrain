import hashlib
import hmac
import requests
import secrets
import time
from django.conf import settings


FLUTTERWAVE_BASE_URL = "https://api.flutterwave.com/v3"


def _get_headers():
    secret_key = settings.FLUTTERWAVE_SECRET_KEY
    if not secret_key:
        raise RuntimeError("FLUTTERWAVE_SECRET_KEY is not set.")
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }


def initialize_transaction(email, amount, reference, redirect_url=None, metadata=None):
    """
    Initialize a Flutterwave transaction.

    Args:
        email: customer email
        amount: amount in NGN (base currency unit)
        reference: unique transaction reference (tx_ref)
        redirect_url: optional URL for Flutterwave to redirect to after payment
        metadata: optional dict attached to the transaction

    Returns:
        dict with success (bool), authorization_url, reference, message
    """
    url = f"{FLUTTERWAVE_BASE_URL}/payments"
    payload = {
        "tx_ref": reference,
        "amount": amount,
        "currency": "NGN",
        "redirect_url": redirect_url,
        "customer": {"email": email},
        "customizations": {
            "title": "Moving Train Chess Academy",
            "description": "Purchase points or book a coaching session",
            "logo": "https://www.themovingtrain.org/static/images/others/logo.svg",
        },
        "meta": metadata or {},
    }

    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "success" and data.get("data"):
            return {
                "success": True,
                "authorization_url": data["data"]["link"],
                "reference": data["data"].get("tx_ref", reference),
                "message": data.get("message", "Transaction initialized"),
            }
        return {
            "success": False,
            "message": data.get("message", "Failed to initialize transaction"),
        }
    except RuntimeError as e:
        return {
            "success": False,
            "message": str(e),
        }
    except requests.HTTPError as e:
        try:
            error_body = response.json()
            message = error_body.get("message", str(e))
        except ValueError:
            message = str(e)
        return {
            "success": False,
            "message": f"Flutterwave error: {message}",
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "message": f"Flutterwave request failed: {e}",
        }


def verify_transaction(reference):
    """
    Verify a Flutterwave transaction by reference (tx_ref).

    Returns:
        dict with success (bool), status, amount, email, reference, message, data
    """
    url = f"{FLUTTERWAVE_BASE_URL}/transactions/verify_by_reference"

    try:
        response = requests.get(
            url,
            headers=_get_headers(),
            params={"tx_ref": reference},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "success" and data.get("data"):
            tx_data = data["data"]
            # Flutterwave amounts are returned in the original currency unit.
            amount = tx_data.get("amount")
            charged_amount = tx_data.get("charged_amount")
            return {
                "success": True,
                "status": tx_data.get("status"),  # e.g. "successful"
                "amount": amount,
                "charged_amount": charged_amount,
                "email": tx_data.get("customer", {}).get("email"),
                "reference": tx_data.get("tx_ref"),
                "transaction_id": tx_data.get("id"),
                "message": data.get("message", "Verification successful"),
                "data": tx_data,
            }
        return {
            "success": False,
            "message": data.get("message", "Verification failed"),
        }
    except RuntimeError as e:
        return {
            "success": False,
            "message": str(e),
        }
    except requests.HTTPError as e:
        try:
            error_body = response.json()
            message = error_body.get("message", str(e))
        except ValueError:
            message = str(e)
        return {
            "success": False,
            "message": f"Flutterwave error: {message}",
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "message": f"Flutterwave request failed: {e}",
        }


def generate_reference(prefix="FLT"):
    """Generate a unique payment reference."""
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(4)}"


def verify_webhook_signature(request_body, signature):
    """
    Verify the Flutterwave webhook signature.

    Flutterwave sends the header `verif-hash` containing a SHA-256 HMAC
    of the request body signed with the webhook secret hash.

    Returns True if the signature is valid or no secret is configured.
    """
    secret = settings.FLUTTERWAVE_WEBHOOK_SECRET
    if not secret:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        request_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

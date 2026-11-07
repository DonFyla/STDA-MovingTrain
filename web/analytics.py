from django.conf import settings
from django.utils import timezone


def claim_purchase_tracking(instance, *, value, transaction_id, item_id, item_name):
    """Claim one browser purchase event for a paid transaction."""
    ads_configured = bool(
        settings.GOOGLE_ADS_CONVERSION_ID and settings.GOOGLE_ADS_CONVERSION_LABEL
    )
    if not (settings.GOOGLE_ANALYTICS_ID or ads_configured):
        return {}

    claimed = instance.__class__.objects.filter(
        pk=instance.pk,
        analytics_tracked_at__isnull=True,
    ).update(analytics_tracked_at=timezone.now())
    if not claimed:
        return {}

    return {
        "google_ads_conversion": {
            "value": value,
            "currency": "NGN",
            "transaction_id": transaction_id,
            "item_id": item_id,
            "item_name": item_name,
        }
    }

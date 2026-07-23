import requests
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Verify Flutterwave configuration and key validity."

    def handle(self, *args, **options):
        secret_key = settings.FLUTTERWAVE_SECRET_KEY
        public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        webhook_secret = settings.FLUTTERWAVE_WEBHOOK_SECRET

        if not secret_key:
            self.stdout.write(self.style.ERROR("FLUTTERWAVE_SECRET_KEY is not set."))
            return

        if not public_key:
            self.stdout.write(self.style.WARNING("FLUTTERWAVE_PUBLIC_KEY is not set."))

        if not webhook_secret:
            self.stdout.write(self.style.WARNING("FLUTTERWAVE_WEBHOOK_SECRET is not set."))

        self.stdout.write(f"Secret key configured: {'yes' if secret_key else 'no'}")
        self.stdout.write(f"Public key configured: {'yes' if public_key else 'no'}")
        self.stdout.write(f"Webhook secret configured: {'yes' if webhook_secret else 'no'}")

        url = "https://api.flutterwave.com/v3/banks/NG"
        try:
            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {secret_key}",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "success":
                self.stdout.write(self.style.SUCCESS("Flutterwave secret key is valid."))
            else:
                self.stdout.write(self.style.ERROR(f"Flutterwave returned: {data.get('message')}"))
        except requests.HTTPError as e:
            self.stdout.write(self.style.ERROR(f"Flutterwave key is invalid or request failed: {e}"))
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Network error: {e}"))

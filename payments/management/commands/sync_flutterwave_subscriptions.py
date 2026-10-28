"""Reconcile recurring subscriptions against Flutterwave (at most once a day).

Backfills renewals the webhook missed (billing fields + receipt email) and
marks subscriptions Flutterwave knows as cancelled. Run on the reminders
container loop; throttled via Redis cache.
"""

from django.core.management.base import BaseCommand

from payments.subscription_sync import run_sync


class Command(BaseCommand):
    help = "Sync subscription status and missed renewal payments from Flutterwave."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if the daily throttle says it is too soon.",
        )

    def handle(self, *args, **options):
        result = run_sync(force=options["force"])
        if result is None:
            self.stdout.write("Skipped (already ran within the last 24 hours).")
            return
        self.stdout.write(
            self.style.SUCCESS(
                "Subscription sync: {status_synced} cancelled, "
                "{billing_synced} billing dates updated, "
                "{backfilled} missed renewals backfilled.".format(**result)
            )
        )

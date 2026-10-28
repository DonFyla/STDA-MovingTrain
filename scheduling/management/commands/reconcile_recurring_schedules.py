"""Align recurring class schedules with paid entitlement.

Keeps paid-for sessions (including for cancelled subscribers), prunes
upcoming sessions a declined renewal did not pay for, and generates the
next block inside the paid window. Run on the reminders container loop.
"""

from django.core.management.base import BaseCommand

from scheduling.recurring import align_due_subscriptions


class Command(BaseCommand):
    help = "Align recurring schedules with each subscription's paid window."

    def handle(self, *args, **options):
        aligned = align_due_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Aligned {aligned} recurring booking(s)."))

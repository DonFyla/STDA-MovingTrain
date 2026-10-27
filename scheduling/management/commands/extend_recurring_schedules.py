"""Roll forward class schedules for active recurring subscriptions.

Runs on a loop alongside send_session_reminders in the reminders container.
Extends any active subscription whose stored sessions are running out, so
monthly billing and the visible class schedule stay in sync.
"""

from django.core.management.base import BaseCommand

from scheduling.recurring import extend_due_subscriptions


class Command(BaseCommand):
    help = "Extend the schedule of active recurring subscriptions whose sessions are running out."

    def handle(self, *args, **options):
        extended = extend_due_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Extended {extended} recurring booking(s)."))

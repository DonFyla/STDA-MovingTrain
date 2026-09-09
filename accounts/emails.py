import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _send_email(subject, to_emails, template_name, context, from_email=None):
    """Render an HTML email template and send to the given recipients."""
    if not to_emails:
        return

    # Normalize to list
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    to_emails = [e for e in to_emails if e]
    if not to_emails:
        return

    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    context.setdefault("site_url", "https://www.themovingtrain.org")

    try:
        html_body = render_to_string(template_name, context)
        text_body = strip_tags(html_body)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=to_emails,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()
    except Exception:
        logger.exception("Failed to send email: %s", subject)


def send_verification_email(user, verify_url):
    """Send the email verification link to a newly registered user."""
    context = {
        "user": user,
        "verify_url": verify_url,
    }
    _send_email(
        subject="Verify your Moving Train account",
        to_emails=user.email,
        template_name="emails/accounts/verify_email.html",
        context=context,
    )

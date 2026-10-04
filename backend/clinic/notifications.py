import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_review_email(*, email, name, decision, reason, role, application_id):
    """Called after commit. SMTP failures must never roll back a review decision."""
    route = "pharmacy" if role == "pharmacist" else "doctor"
    try:
        send_mail(
            "Your MedyLink provider application was reviewed",
            f"Hello {name},\n\nYour provider application is now {decision}.\n"
            f"Review reason: {reason}\n\nSign in to view the decision and next steps:\n"
            f"{settings.FRONTEND_ORIGIN.rstrip('/')}/{route}\n",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception:
        # Keep email addresses, review content, and SMTP credentials out of logs.
        logger.warning(
            "Provider decision email delivery failed for application %s.",
            application_id,
        )

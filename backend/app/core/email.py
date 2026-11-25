"""
Outbound email.

EMAIL_BACKEND:
  disabled (default) — features that must email a secret (invitations, password
                       reset) return 503. Nothing is pretended to be sent and no
                       token is exposed as a fallback.
  smtp               — SMTP_HOST/SMTP_PORT[/SMTP_USERNAME/SMTP_PASSWORD/SMTP_STARTTLS].
                       For local development point it at a mail catcher such as
                       Mailpit (docker compose service `mailpit`, UI on :8025).
  memory             — test-only outbox; refused unless ENVIRONMENT=test.

Message bodies contain secret links and are never logged.
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OutboundEmail:
    to: str
    subject: str
    body: str


OUTBOX: list[OutboundEmail] = []  # memory backend only


class EmailUnavailable(Exception):
    pass


def _backend() -> str:
    backend = os.getenv("EMAIL_BACKEND", "disabled").strip().lower()
    if backend == "memory" and settings.ENVIRONMENT != "test":
        logger.error("EMAIL_BACKEND=memory is only allowed when ENVIRONMENT=test; treating as disabled")
        return "disabled"
    if backend not in ("disabled", "smtp", "memory"):
        return "disabled"
    if backend == "smtp" and not os.getenv("SMTP_HOST"):
        return "disabled"
    return backend


def email_delivery_available() -> bool:
    return _backend() != "disabled"


def send_email(to: str, subject: str, body: str) -> None:
    backend = _backend()
    if backend == "disabled":
        raise EmailUnavailable("Email delivery is not configured.")
    if backend == "memory":
        OUTBOX.append(OutboundEmail(to=to, subject=subject, body=body))
        return

    msg = EmailMessage()
    msg["From"] = os.getenv("EMAIL_FROM", "Gripper <no-reply@localhost>")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if os.getenv("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes"):
                smtp.starttls()
            user = os.getenv("SMTP_USERNAME")
            if user:
                smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("SMTP delivery failed (%s)", type(exc).__name__)
        raise EmailUnavailable("Email delivery failed.") from exc
    logger.info("Email sent (subject=%r)", subject)


def app_link(fragment: str) -> str:
    """
    Builds a frontend link carrying a secret in the URL *fragment* (after '#').
    Fragments are not sent to servers or included in Referer headers.
    """
    base = os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/app#{fragment}"

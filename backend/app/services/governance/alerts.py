import logging
from typing import Any

logger = logging.getLogger("governance_alerts")


def dispatch_violation_alert(event: Any):
    """
    Alert broker for new compliance violations.
    Logs a structured warning. In production, extend this to send to
    Slack, PagerDuty, or an audit webhook.
    """
    details = event.details_json
    logger.warning(
        "[IPS VIOLATION] severity=%s type=%s message=%s",
        event.severity.upper(),
        event.event_type,
        details.get("message"),
    )


def dispatch_resolution_alert(event: Any):
    """
    Alert broker for resolved violations.
    """
    details = event.details_json
    item = details.get("ticker") or details.get("sector") or "Portfolio"
    logger.info(
        "[IPS RESOLVED] type=%s item=%s",
        event.event_type,
        item,
    )

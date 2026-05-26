import logging
from typing import Any

logger = logging.getLogger("governance_alerts")

def dispatch_violation_alert(event: Any):
    """
    Alert broker for new compliance violations.
    Dispatches warnings to loggers and console brokers.
    """
    details = event.details_json
    msg = (
        f"🚨 [IPS VIOLATION] Severity: {event.severity.upper()} | "
        f"Type: {event.event_type} | Message: {details.get('message')}"
    )
    logger.warning(msg)
    print(msg)

def dispatch_resolution_alert(event: Any):
    """
    Alert broker for resolved violations.
    Dispatches information to audit databases and console brokers.
    """
    details = event.details_json
    item = details.get('ticker') or details.get('sector') or 'Portfolio'
    msg = f"✅ [IPS RESOLVED] Type: {event.event_type} | Item: {item}"
    logger.info(msg)
    print(msg)

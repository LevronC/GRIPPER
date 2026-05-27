"""
Centralized error helpers for FastAPI route handlers.

Prevents raw exception messages from leaking implementation details to API
consumers in production. In debug mode (DEBUG_PRINT_CODES), the original
error is included in the detail for easier local troubleshooting.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def internal_error(exc: Exception, operation: str = "operation") -> dict[str, Any]:
    """
    Returns a kwargs dict suitable for raising an HTTPException with a safe
    error detail that does not expose stack traces or database internals.

    Usage:
        raise HTTPException(status_code=500, **internal_error(e, "semantic_search"))
    """
    logger.exception("Unhandled error during %s: %s", operation, exc)

    try:
        from app.core.config import settings
        debug = settings.DEBUG_PRINT_CODES
    except Exception:
        debug = False

    detail = (
        f"Internal server error during {operation}: {exc}"
        if debug
        else f"An internal error occurred. Please try again later. (ref: {operation})"
    )
    return {"detail": detail}

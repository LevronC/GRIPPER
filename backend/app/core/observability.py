import json
import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger("gripper_observability")

logging.basicConfig(level=logging.INFO)


def log_json_metric(
    operation: str,
    duration_ms: float,
    status: str,
    error_type: Optional[str] = None,
) -> None:
    """Structured timing log. Records only the operation, duration, status and error class."""
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "error_type": error_type,
    }))


def observe_time(operation_name: str) -> Callable:
    """
    Measures latency with a monotonic clock and logs it. Deliberately does NOT log
    arguments or exception messages: those can contain search queries, document text or
    portfolio data (the previous version printed keyword arguments to stdout).
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            status, error_type = "success", None
            try:
                return func(*args, **kwargs)
            except Exception as e:
                status, error_type = "error", type(e).__name__
                raise
            finally:
                log_json_metric(operation_name, (time.perf_counter() - start) * 1000.0, status, error_type)
        return wrapper
    return decorator

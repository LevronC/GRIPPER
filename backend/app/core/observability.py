import time
import json
import logging
from functools import wraps
from datetime import datetime
from typing import Callable, Any

logger = logging.getLogger("gripper_observability")

# Configure logger to only output JSON or custom logs
logging.basicConfig(level=logging.INFO)

def log_json_metric(
    operation: str,
    duration_ms: float,
    status: str,
    error_message: str = None,
    metadata: dict = None
) -> None:
    """
    Emits a structured JSON log containing telemetry metrics.
    """
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "error_message": error_message,
        "metadata": metadata or {}
    }
    # Log via standard logging system
    logger.info(json.dumps(log_data))
    # Print to console for immediate visibility during tests
    print(f"📊 [OBSERVABILITY] {json.dumps(log_data)}")

def observe_time(operation_name: str) -> Callable:
    """
    A Python decorator to measure and log function execution latency as structured JSON.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            status = "success"
            error_message = None
            try:
                return func(*args, **kwargs)
            except Exception as e:
                status = "error"
                error_message = str(e)
                raise
            finally:
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000.0
                
                # Dynamic metadata extraction based on method context
                metadata = {}
                if kwargs:
                    # Mask sensitive information, serialize basic values
                    for k, v in kwargs.items():
                        if isinstance(v, (str, int, float, bool)):
                            metadata[k] = v
                log_json_metric(operation_name, duration_ms, status, error_message, metadata)
        return wrapper
    return decorator

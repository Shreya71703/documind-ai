import json
import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger("rag_structured")

# Configure logging formatter for console if not already configured
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def log_structured(
    level: int,
    event_name: str,
    operation: str,
    duration_ms: float = None,
    outcome: str = "success",
    error_category: str = None,
    provider: str = None,
    model: str = None,
    document_id: str = None,
    session_id: str = None,
    user_id: str = None,
    extra: dict = None
):
    log_data = {
        "event_name": event_name,
        "operation": operation,
        "request_id": request_id_var.get(),
        "outcome": outcome
    }
    if duration_ms is not None:
        log_data["duration_ms"] = round(duration_ms, 2)
    if error_category is not None:
        log_data["error_category"] = error_category
    if provider is not None:
        log_data["provider"] = provider
    if model is not None:
        log_data["model"] = model
    if document_id is not None:
        log_data["document_id"] = str(document_id)
    if session_id is not None:
        log_data["session_id"] = str(session_id)
    if user_id is not None:
        log_data["user_id"] = str(user_id)
    if extra:
        log_data.update(extra)

    # Serialized output
    logger.log(level, json.dumps(log_data))

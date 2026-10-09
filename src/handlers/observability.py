import json
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)
SAFE_FIELDS = {
    "command",
    "component",
    "discord_error_code",
    "discord_http_status",
    "event",
    "execution_arn",
    "latency_ms",
    "outcome",
    "run_id",
}


def emit(event: str, **fields: Any) -> None:
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if key in SAFE_FIELDS and value is not None})
    LOGGER.info(json.dumps(payload, sort_keys=True))

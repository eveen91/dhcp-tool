"""Allowlisted metadata only: no message interpolation or exception dumps."""

import json
import logging

EVENTS = {
    "login_success",
    "login_failed",
    "login_limited",
    "logout",
    "api_error",
    "access_denied",
    "access_changed",
    "application_message",
}


class SafeFormatter(logging.Formatter):
    def format(self, record):
        event = getattr(record, "event", "application_message")
        data = {
            "level": record.levelname,
            "event": event if event in EVENTS else "application_message",
        }
        status = getattr(record, "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            data["status"] = status
        return json.dumps(data, ensure_ascii=True)

"""PII masking for logs, traces and the audit log (R9 / E4)."""

from __future__ import annotations

import logging
import re
from typing import Any

PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("PHONE", re.compile(r"(?<![\w$])\+?\d[\d\s().-]{7,}\d\b")),
    ("TOKEN", re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9]{20,})")),
]
SECRET_KEYS = {"password", "access_token", "refresh_token", "authorization", "api_key", "token", "client_secret", "ciphertext"}


def mask_text(text: str) -> str:
    for label, rx in PATTERNS:
        text = rx.sub(f"[{label}]", text)
    return text


def mask(obj: Any) -> Any:
    """Recursively mask strings; drop values under secret-looking keys entirely."""
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in SECRET_KEYS else mask(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask(v) for v in obj]
    return obj


class PIIFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_text(record.msg)
        if record.args:
            record.args = tuple(mask(a) for a in record.args) if isinstance(record.args, tuple) else mask(record.args)
        return True


def install_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(PIIFilter())

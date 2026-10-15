"""Portable timestamps, identifiers and serialization values for stored records."""
from uuid import UUID, uuid4
from datetime import datetime, timezone
import time, re

def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

def uuid7():
    random = uuid4().int
    return str(UUID(int=(int(time.time() * 1000) << 80) | (7 << 76) | (((random >> 64) & 0xfff) << 64) | (2 << 62) | (random & ((1 << 62) - 1))))

def redact(value):
    if isinstance(value, str):
        return re.sub(r'(?i)(authorization\s*[:=]\s*bearer\s+|api[_-]?key["\s]*[:=]["\s]*)([^\s"\x27,}]+)', r'\1[REDACTED]', value)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

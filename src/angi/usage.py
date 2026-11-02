import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

logger = logging.getLogger("angi.usage")

# ip_hash tells requests from one visitor apart from another's without storing who
# they are. With a known salt (the old default "angi" is in the repo) any IPv4 hash
# is reversed by hashing all 2^32 addresses, and now that rate limiting keys on the
# real visitor (CF-Connecting-IP) the log would hold reversible addresses, while
# the page promises "không lưu gì cả". This salt lives only in memory.
_PROCESS_SALT = secrets.token_hex(16)


def ip_hash(ip: str) -> str:
    salt = settings.ip_hash_salt or _PROCESS_SALT
    return hashlib.sha256((salt + ip).encode()).hexdigest()[:12]


def log_usage(
    *,
    budget: str | None,
    mood: str | None,
    tier: int,
    dish: str,
    weather: str | None,
    fallback: bool,
    status: str,
    duration_ms: int,
    ip: str,
) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": "suggest",
        "budget": budget,
        "mood": mood,
        "tier": tier,
        "dish": dish,
        "weather": weather,
        "fallback": fallback,
        "status": status,
        "duration_ms": duration_ms,
        "ip_hash": ip_hash(ip),
    }
    line = json.dumps(rec, ensure_ascii=False)
    logger.info(line)
    try:
        path = Path(settings.usage_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        logger.warning("usage file write failed: %s", e)

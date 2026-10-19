import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

logger = logging.getLogger("angi.usage")


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
        "ip_hash": hashlib.sha256((settings.ip_hash_salt + ip).encode()).hexdigest()[:12],
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

import hashlib
import json
from pathlib import Path

from angi import usage
from angi.config import settings


def _sha12(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def test_default_ip_hash_cannot_be_reversed_with_a_known_salt(monkeypatch):
    monkeypatch.setattr(settings, "ip_hash_salt", "")
    h = usage.ip_hash("203.0.113.7")
    assert h == usage.ip_hash("203.0.113.7")  # one visitor groups within a run
    assert h != usage.ip_hash("203.0.113.8")  # and differs from the next visitor
    # not the hash anyone can recompute from the repo's old default or no salt
    for known_salt in ("angi", ""):
        assert h != _sha12(known_salt + "203.0.113.7")


def test_explicit_salt_is_used(monkeypatch):
    monkeypatch.setattr(settings, "ip_hash_salt", "s3cret")
    assert usage.ip_hash("203.0.113.7") == _sha12("s3cret203.0.113.7")


def test_usage_log_stores_only_the_hash(monkeypatch):
    monkeypatch.setattr(settings, "ip_hash_salt", "")
    usage.log_usage(
        budget=None, mood=None, tier=0, dish="Phở bò", weather=None,
        fallback=False, status="ok", duration_ms=5, ip="203.0.113.7",
    )
    text = Path(settings.usage_file).read_text()
    assert "203.0.113.7" not in text
    assert json.loads(text)["ip_hash"] == usage.ip_hash("203.0.113.7")

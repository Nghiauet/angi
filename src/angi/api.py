import asyncio
import ipaddress
import json
import logging
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import weather
from .config import settings
from .lines import canned_line, sanitize, sass_tier, validate
from .ollama_client import OllamaBadResponse, OllamaClient, OllamaDown, OllamaError, OllamaTimeout
from .picker import pick
from .prompts import build_messages
from .usage import log_usage

router = APIRouter()
logger = logging.getLogger(__name__)

ERR_BAD_REQUEST = "Yêu cầu không hợp lệ."
ERR_TOO_LARGE = "Yêu cầu quá lớn."
ERR_MEDIA_TYPE = "Chỉ nhận JSON (Content-Type: application/json)."
ERR_RATE = "Từ từ thôi! Đổi món gì mà nhanh thế. Đợi một phút nhé."

# A real body is a few hundred bytes (budget/mood/city + rejected dish names);
# 64 KB still fits ~2000 rejected names. Anything bigger is abuse.
MAX_BODY_BYTES = 64 * 1024
# Rejected names the picker excludes and the prompt sees: the MOST RECENT ones.
MAX_REJECTED_KEPT = 30
MAX_NAME_CHARS = 60

_VALID_BUDGET = {"20", "50", "max"}
_VALID_MOOD = {"vui", "met", "deadline"}
_VALID_CITY = {"hn", "sg"}
_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class _BadBody(Exception):
    def __init__(self, status: int, error: str):
        self.status = status
        self.error = error


async def _read_json(request: Request):
    """Parse the JSON body, refusing anything over MAX_BODY_BYTES without
    buffering it (uvicorn itself has no body-size limit)."""
    # Require a JSON content type. Without this, any other website could make
    # its visitors' browsers POST here as a CORS "simple request" (text/plain,
    # or a Blob with no type) — no preflight, a fresh IP per visitor, and GPU
    # work for us. application/json forces a preflight, which this app (no
    # CORS headers) fails, so browsers never send the cross-site request.
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != "application/json":
        raise _BadBody(415, ERR_MEDIA_TYPE)
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_BODY_BYTES:
                raise _BadBody(413, ERR_TOO_LARGE)
        except ValueError:
            raise _BadBody(400, ERR_BAD_REQUEST) from None
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY_BYTES:
            raise _BadBody(413, ERR_TOO_LARGE)
    try:
        return json.loads(raw)
    except ValueError:  # JSONDecodeError and UnicodeDecodeError
        raise _BadBody(400, ERR_BAD_REQUEST) from None


def _enum(value, allowed: set[str]) -> str | None:
    # isinstance first: `[] in a_set` raises TypeError (unhashable) -> HTTP 500
    return value if isinstance(value, str) and value in allowed else None


def _visitor_key(request: Request) -> str:
    """Rate-limit key for the real visitor.

    Requests arrive cloudflared -> nginx (127.0.0.1) -> here, and nginx sets
    X-Real-IP to $remote_addr, i.e. 127.0.0.1 for EVERY visitor, so keying on it
    made the "per-IP" limit one global bucket. Cloudflare's CF-Connecting-IP
    carries the visitor address (clients can't override it through Cloudflare,
    and this app only listens on loopback). IPv6 is keyed per /64, because one
    host can rotate through a whole /64.
    """
    raw = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else "unknown")
    ).strip()
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return raw[:64] or "unknown"
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return f"{ipaddress.ip_network(f'{ip}/64', strict=False).network_address}/64"
    return str(ip)


def _client_date(raw) -> date:
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(_TZ).date()


@router.post("/api/suggest")
async def suggest(request: Request):
    try:
        body = await _read_json(request)
    except _BadBody as e:
        return JSONResponse(status_code=e.status, content={"error": e.error})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": ERR_BAD_REQUEST})

    budget = _enum(body.get("budget"), _VALID_BUDGET)
    mood = _enum(body.get("mood"), _VALID_MOOD)
    city = _enum(body.get("city"), _VALID_CITY)
    raw_rejected = body.get("rejected")
    if raw_rejected is None:
        raw_rejected = []
    if not isinstance(raw_rejected, list):
        return JSONResponse(status_code=400, content={"error": ERR_BAD_REQUEST})
    names = [r[:MAX_NAME_CHARS] for r in raw_rejected if isinstance(r, str)]
    rejected_count = len(names)
    # keep the most recent names: the frontend appends, so the old [:30] kept
    # the oldest ones and let dishes rejected after #30 come straight back
    rejected = names[-MAX_REJECTED_KEPT:]
    today = _client_date(body.get("client_date"))

    ip = _visitor_key(request)
    state = request.app.state
    if not state.rpm.allow(ip):
        return JSONResponse(status_code=429, content={"error": ERR_RATE})

    started = time.monotonic()
    wx = await weather.current(city)
    dish = pick(budget, wx, rejected)
    tier = sass_tier(rejected_count)
    broke = today.day >= 25 and budget == "20"

    line, status = await _generate_line(
        state, dish.name, tier, budget, mood, wx, rejected, rejected_count, broke
    )
    fallback = status not in ("ok", "ok_retry")
    duration_ms = int((time.monotonic() - started) * 1000)
    log_usage(
        budget=budget, mood=mood, tier=tier, dish=dish.name,
        weather=wx if city else None, fallback=fallback, status=status,
        duration_ms=duration_ms, ip=ip,
    )
    return JSONResponse(
        content={
            "dish": dish.name,
            "line": line,
            "tier": tier,
            "fallback": fallback,
            "price_tier": dish.price_tier,
            "category": dish.category,
            "weather": wx if city else None,
            "broke": broke,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/weather")
async def weather_now(city: str | None = None):
    """Cached weather for the city chips — never touches the GPU."""
    if city not in _VALID_CITY:
        return JSONResponse(status_code=400, content={"error": ERR_BAD_REQUEST})
    fit, temp = await weather.current_full(city)
    return JSONResponse(
        content={"weather": fit, "temp_c": temp},
        headers={"Cache-Control": "no-store"},
    )


async def _generate_line(state, dish_name, tier, budget, mood, wx, rejected, rejected_count, broke):
    """LLM line with the canned pool as an unbreakable floor. One calmer retry
    after a validation reject — most rejects are language drift, and a second
    pass at lower temperature usually lands (status "ok_retry").

    The whole thing, queue wait included, runs under line_deadline_s: the
    per-call HTTP timeout alone let requests wait behind a busy GPU queue
    for minutes (Cloudflare gives up at 100 s)."""
    gate = state.gate

    def canned():
        return canned_line(tier, dish_name, broke, wx)

    if gate.full:
        return canned(), "canned_queue"
    messages = build_messages(
        dish=dish_name, tier=tier, budget=budget, mood=mood,
        weather=wx, rejected=rejected, rejected_count=rejected_count, broke=broke,
    )
    try:
        async with asyncio.timeout(settings.line_deadline_s):
            line, status = await _llm_line(state, messages, dish_name)
    except TimeoutError:
        return canned(), "canned_timeout"
    except Exception:  # the floor: an LLM problem must never become a 500
        logger.exception("line generation failed")
        return canned(), "canned_error"
    return (line, status) if line is not None else (canned(), status)


class _OverBudget(Exception):
    """Global LLM budget (llm_rpm_global) used up for this minute."""


async def _llm_line(state, messages, dish_name) -> tuple[str | None, str]:
    """(line, status); line is None when the caller should use a canned line."""
    gate = state.gate
    ollama: OllamaClient = state.ollama

    if ollama.known_down and not await ollama.ping():
        return None, "canned_down"
    gen_started = time.monotonic()

    async def attempt(temperature: float | None):
        if not state.llm_budget.allow("all"):
            raise _OverBudget()
        gate.waiting += 1
        try:
            async with gate.sem:
                raw = await ollama.complete(messages, temperature=temperature)
        finally:
            gate.waiting -= 1
        return validate(sanitize(raw), dish_name)

    try:
        line = await attempt(None)
    except _OverBudget:
        return None, "canned_busy"
    except OllamaDown:
        return None, "canned_down"
    except OllamaTimeout:
        return None, "canned_timeout"
    except OllamaBadResponse as e:
        logger.warning("ollama gave no usable line: %s", e)
        return None, "canned_error"
    if line is not None:
        return line, "ok"

    elapsed = time.monotonic() - gen_started
    if elapsed < settings.retry_budget_s and not gate.full:
        try:
            line = await attempt(settings.retry_temperature)
        except (OllamaError, _OverBudget):
            return None, "canned_reject"
        if line is not None:
            return line, "ok_retry"
    return None, "canned_reject"

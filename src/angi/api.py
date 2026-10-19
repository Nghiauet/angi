import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import weather
from .config import settings
from .lines import canned_line, sanitize, sass_tier, validate
from .ollama_client import OllamaClient, OllamaDown, OllamaTimeout
from .picker import pick
from .prompts import build_messages
from .usage import log_usage

router = APIRouter()

ERR_BAD_REQUEST = "Yêu cầu không hợp lệ."
ERR_RATE = "Từ từ thôi! Đổi món gì mà nhanh thế. Đợi một phút nhé."

_VALID_BUDGET = {"20", "50", "max"}
_VALID_MOOD = {"vui", "met", "deadline"}
_VALID_CITY = {"hn", "sg"}
_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


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
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": ERR_BAD_REQUEST})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": ERR_BAD_REQUEST})

    budget = body.get("budget") if body.get("budget") in _VALID_BUDGET else None
    mood = body.get("mood") if body.get("mood") in _VALID_MOOD else None
    city = body.get("city") if body.get("city") in _VALID_CITY else None
    raw_rejected = body.get("rejected")
    if raw_rejected is None:
        raw_rejected = []
    if not isinstance(raw_rejected, list):
        return JSONResponse(status_code=400, content={"error": ERR_BAD_REQUEST})
    rejected = [r[:60] for r in raw_rejected if isinstance(r, str)][:30]
    today = _client_date(body.get("client_date"))

    ip = request.headers.get("x-real-ip") or (
        request.client.host if request.client else "unknown"
    )
    state = request.app.state
    if not state.rpm.allow(ip):
        return JSONResponse(status_code=429, content={"error": ERR_RATE})

    started = time.monotonic()
    wx = await weather.current(city)
    dish = pick(budget, wx, rejected)
    tier = sass_tier(len(rejected))
    broke = today.day >= 25 and budget == "20"

    line, status = await _generate_line(state, dish.name, tier, budget, mood, wx, rejected, broke)
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


async def _generate_line(state, dish_name, tier, budget, mood, wx, rejected, broke):
    """LLM line with the canned pool as an unbreakable floor. One calmer retry
    after a validation reject — most rejects are language drift, and a second
    pass at lower temperature usually lands (status "ok_retry")."""
    gate = state.gate
    ollama: OllamaClient = state.ollama

    def canned():
        return canned_line(tier, dish_name, broke, wx)

    if gate.full:
        return canned(), "canned_queue"
    if ollama.known_down and not await ollama.ping():
        return canned(), "canned_down"

    messages = build_messages(
        dish=dish_name, tier=tier, budget=budget, mood=mood,
        weather=wx, rejected=rejected, broke=broke,
    )
    gen_started = time.monotonic()

    async def attempt(temperature: float | None):
        gate.waiting += 1
        try:
            async with gate.sem:
                raw = await ollama.complete(messages, temperature=temperature)
        finally:
            gate.waiting -= 1
        return validate(sanitize(raw), dish_name)

    try:
        line = await attempt(None)
    except OllamaDown:
        return canned(), "canned_down"
    except OllamaTimeout:
        return canned(), "canned_timeout"
    if line is not None:
        return line, "ok"

    elapsed = time.monotonic() - gen_started
    if elapsed < settings.retry_budget_s and not gate.full:
        try:
            line = await attempt(settings.retry_temperature)
        except (OllamaDown, OllamaTimeout):
            return canned(), "canned_reject"
        if line is not None:
            return line, "ok_retry"
    return canned(), "canned_reject"

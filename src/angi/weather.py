import logging
import time

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_COORDS = {"hn": (21.03, 105.85), "sg": (10.78, 106.70)}
_RAIN_CODES = set(range(51, 68)) | set(range(80, 83)) | set(range(95, 100))
_cache: dict[str, tuple[float, str, float | None]] = {}


async def current(city: str | None) -> str:
    """Return "rain" | "hot" | "any". Never raises; degrades to "any"."""
    fit, _ = await current_full(city)
    return fit


async def current_full(city: str | None) -> tuple[str, float | None]:
    """Return (fit, temp_c). Never raises; degrades to ("any", None)."""
    if not settings.weather_enabled or city not in _COORDS:
        return "any", None
    now = time.monotonic()
    hit = _cache.get(city)
    if hit and now < hit[0]:
        return hit[1], hit[2]
    try:
        fit, temp = await _fetch(city)
        ttl = settings.weather_cache_s
    except Exception as e:
        # Cache the failure briefly too: otherwise, while open-meteo is down,
        # every request with a city waits out the 3 s timeout again, and the
        # unthrottled /api/weather turns each visitor hit into an outbound call.
        logger.warning("weather fetch failed for %s: %s", city, e)
        fit, temp, ttl = "any", None, settings.weather_retry_s
    _cache[city] = (now + ttl, fit, temp)
    return fit, temp


async def _fetch(city: str) -> tuple[str, float | None]:
    """Raises on any network or data problem; current_full degrades."""
    lat, lon = _COORDS[city]
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,precipitation,weather_code"
    )
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return _classify(resp.json()["current"])


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _classify(cur) -> tuple[str, float | None]:
    # open-meteo may send null for a missing reading; the old code compared
    # None > 0.2 OUTSIDE its try block and turned that into an HTTP 500
    if not isinstance(cur, dict):
        raise ValueError(f"unexpected 'current' block: {cur!r:.100}")
    temp = _num(cur.get("temperature_2m"))
    precip = _num(cur.get("precipitation")) or 0.0
    code = _num(cur.get("weather_code"))
    if precip > 0.2 or (code is not None and code.is_integer() and int(code) in _RAIN_CODES):
        return "rain", temp
    if temp is not None and temp >= 34:
        return "hot", temp
    return "any", temp

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
    if hit and now - hit[0] < settings.weather_cache_s:
        return hit[1], hit[2]
    fit, temp = await _fetch(city)
    _cache[city] = (now, fit, temp)
    return fit, temp


async def _fetch(city: str) -> tuple[str, float | None]:
    lat, lon = _COORDS[city]
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,precipitation,weather_code"
    )
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            cur = resp.json()["current"]
    except Exception as e:
        logger.warning("weather fetch failed for %s: %s", city, e)
        return "any", None
    temp = cur.get("temperature_2m")
    if cur.get("precipitation", 0) > 0.2 or cur.get("weather_code") in _RAIN_CODES:
        return "rain", temp
    if (temp or 0) >= 34:
        return "hot", temp
    return "any", temp

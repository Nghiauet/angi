import pytest

from angi import weather
from angi.config import settings


@pytest.fixture(autouse=True)
def clear_cache():
    weather._cache.clear()
    yield
    weather._cache.clear()


@pytest.mark.anyio
async def anyio_backend():
    return "asyncio"


def test_disabled_returns_any(monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, "weather_enabled", False)
    assert asyncio.run(weather.current("hn")) == "any"


def test_unknown_city_returns_any(monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, "weather_enabled", True)
    assert asyncio.run(weather.current(None)) == "any"
    assert asyncio.run(weather.current("paris")) == "any"


def test_fetch_failure_degrades(monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, "weather_enabled", True)

    async def broken_fetch(city):
        return "any", None

    monkeypatch.setattr(weather, "_fetch", broken_fetch)
    assert asyncio.run(weather.current("hn")) == "any"
    assert asyncio.run(weather.current_full("hn")) == ("any", None)


def test_cache_used(monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, "weather_enabled", True)
    calls = []

    async def fake_fetch(city):
        calls.append(city)
        return "rain", 27.5

    monkeypatch.setattr(weather, "_fetch", fake_fetch)
    assert asyncio.run(weather.current("hn")) == "rain"
    assert asyncio.run(weather.current_full("hn")) == ("rain", 27.5)
    assert len(calls) == 1  # second call served from cache


_REAL_ASYNC_CLIENT = weather.httpx.AsyncClient


def _serve(monkeypatch, handler):
    """Route weather._fetch's httpx client to a MockTransport (no network)."""
    import httpx

    monkeypatch.setattr(
        weather.httpx,
        "AsyncClient",
        lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
    )


def test_real_fetch_classifies(monkeypatch):
    import asyncio

    import httpx

    monkeypatch.setattr(settings, "weather_enabled", True)
    payloads = {
        "rain": {"temperature_2m": 26.0, "precipitation": 1.2, "weather_code": 3},
        "hot": {"temperature_2m": 36.5, "precipitation": 0.0, "weather_code": 1},
        "any": {"temperature_2m": 29.0, "precipitation": 0.0, "weather_code": 2},
    }
    for expected, cur in payloads.items():
        weather._cache.clear()
        _serve(monkeypatch, lambda req, cur=cur: httpx.Response(200, json={"current": cur}))
        assert asyncio.run(weather.current_full("hn")) == (expected, cur["temperature_2m"])


def test_null_or_odd_fields_never_raise(monkeypatch):
    import asyncio

    import httpx

    monkeypatch.setattr(settings, "weather_enabled", True)
    for body in (
        {"current": {"temperature_2m": 31.0, "precipitation": None, "weather_code": 3}},
        {"current": {"temperature_2m": None, "precipitation": None, "weather_code": None}},
        {"current": {"temperature_2m": "hot", "precipitation": "lots", "weather_code": [61]}},
        {"current": None},
        {},
        [],
    ):
        weather._cache.clear()
        _serve(monkeypatch, lambda req, body=body: httpx.Response(200, json=body))
        fit, temp = asyncio.run(weather.current_full("sg"))
        assert fit in ("rain", "hot", "any")
        assert temp is None or isinstance(temp, float)


def test_failure_is_cached_briefly(monkeypatch):
    import asyncio
    import time

    import httpx

    monkeypatch.setattr(settings, "weather_enabled", True)
    monkeypatch.setattr(settings, "weather_retry_s", 0.2)
    calls = []

    def down(req):
        calls.append(1)
        raise httpx.ConnectError("open-meteo down")

    _serve(monkeypatch, down)
    assert asyncio.run(weather.current_full("hn")) == ("any", None)
    assert asyncio.run(weather.current_full("hn")) == ("any", None)
    assert len(calls) == 1  # second call did not hit the network again
    time.sleep(0.25)
    asyncio.run(weather.current_full("hn"))
    assert len(calls) == 2  # retried after weather_retry_s

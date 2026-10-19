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

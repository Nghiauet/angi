import pytest
from starlette.testclient import TestClient

from angi.config import settings
from angi.main import create_app
from angi.ollama_client import OllamaClient


@pytest.fixture(autouse=True)
def usage_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "usage_file", str(tmp_path / "usage.jsonl"))
    monkeypatch.setattr(settings, "weather_enabled", False)  # no network in tests


@pytest.fixture
def make_client(monkeypatch):
    """Build a TestClient whose OllamaClient.complete is replaced by `fn(messages) -> str`."""

    def _make(fn):
        async def fake_complete(self, messages, num_predict=None, temperature=None):
            return fn(messages)

        async def fake_warmup(self):
            return None

        monkeypatch.setattr(OllamaClient, "complete", fake_complete)
        monkeypatch.setattr(OllamaClient, "warmup", fake_warmup)
        app = create_app()
        client = TestClient(app)
        client.__enter__()
        return app, client

    made = []

    def _make_tracked(fn):
        app, client = _make(fn)
        made.append(client)
        return app, client

    yield _make_tracked
    for c in made:
        c.__exit__(None, None, None)

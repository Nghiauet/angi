"""OllamaClient error mapping, against httpx.MockTransport (never the real Ollama)."""

import asyncio

import httpx
import pytest

from angi.ollama_client import OllamaBadResponse, OllamaClient, OllamaDown, OllamaTimeout

MSGS = [{"role": "user", "content": "chào"}]


def run_complete(handler):
    async def go():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://ollama.test"
        ) as http:
            client = OllamaClient(http)
            try:
                return await client.complete(MSGS), client
            except Exception as e:
                e.client = client
                raise

    return asyncio.run(go())


def test_ok():
    line, client = run_complete(lambda req: httpx.Response(200, json={"message": {"content": "Phở nhé!"}}))
    assert line == "Phở nhé!"
    assert client.known_down is False


def test_model_missing_404_is_bad_response():
    with pytest.raises(OllamaBadResponse) as ei:
        run_complete(lambda req: httpx.Response(404, json={"error": "model 'qwen2.5' not found"}))
    assert ei.value.client.known_down is False  # server is up; ping won't help


@pytest.mark.parametrize(
    "body",
    [b"not json", b"{}", b'{"message": null}', b'{"message": {"content": 42}}', b"[]"],
)
def test_malformed_body_is_bad_response(body):
    with pytest.raises(OllamaBadResponse):
        run_complete(lambda req: httpx.Response(200, content=body))


def test_5xx_is_down():
    with pytest.raises(OllamaDown) as ei:
        run_complete(lambda req: httpx.Response(500, text="loading model failed"))
    assert ei.value.client.known_down is True


@pytest.mark.parametrize(
    "exc", [httpx.RemoteProtocolError("peer closed"), httpx.ReadError("reset"), httpx.ConnectError("refused")]
)
def test_dropped_connection_is_down(exc):
    def handler(req):
        raise exc

    with pytest.raises(OllamaDown) as ei:
        run_complete(handler)
    assert ei.value.client.known_down is True


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.WriteTimeout("slow"), httpx.PoolTimeout("busy")])
def test_timeouts_are_timeout(exc):
    def handler(req):
        raise exc

    with pytest.raises(OllamaTimeout):
        run_complete(handler)

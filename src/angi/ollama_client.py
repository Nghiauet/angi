import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """No usable line from Ollama. Callers fall back to a canned line."""


class OllamaDown(OllamaError):
    pass


class OllamaTimeout(OllamaError):
    pass


class OllamaBadResponse(OllamaError):
    """Ollama answered, but not with a line: a 4xx (e.g. 404 when the model
    was removed or renamed) or a body that isn't the /api/chat shape."""


class OllamaClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.known_down = False

    async def complete(
        self,
        messages: list[dict],
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str:
        payload = {
            "model": settings.model,
            "messages": messages,
            "stream": False,
            "keep_alive": settings.keep_alive,
            "options": {
                "temperature": settings.temperature if temperature is None else temperature,
                "num_ctx": settings.num_ctx,
                "num_predict": num_predict or settings.num_predict,
            },
        }
        try:
            resp = await self.client.post("/api/chat", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            self.known_down = True
            raise OllamaDown() from e
        except httpx.TimeoutException as e:  # read / write / pool timeout
            raise OllamaTimeout() from e
        except httpx.HTTPError as e:
            # connection dropped mid-request (ReadError, RemoteProtocolError):
            # typically Ollama restarting or being upgraded
            self.known_down = True
            raise OllamaDown() from e
        if resp.status_code >= 500:
            self.known_down = True
            raise OllamaDown()
        self.known_down = False
        if resp.status_code != 200:
            raise OllamaBadResponse(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            content = resp.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as e:
            raise OllamaBadResponse(f"malformed /api/chat body: {resp.text[:200]}") from e
        if not isinstance(content, str):
            raise OllamaBadResponse(f"non-string content: {content!r:.200}")
        return content

    async def ping(self) -> bool:
        try:
            resp = await self.client.get("/api/version", timeout=2.0)
            ok = resp.status_code == 200
        except httpx.HTTPError:
            ok = False
        self.known_down = not ok
        return ok

    async def warmup(self) -> None:
        """Page the model into VRAM at startup. Never crashes the app."""
        try:
            await self.complete([{"role": "user", "content": "chào"}], num_predict=1)
            logger.info("model warmup complete")
        except Exception as e:
            logger.warning("model warmup failed: %s", e)

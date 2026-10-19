import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class OllamaDown(Exception):
    pass


class OllamaTimeout(Exception):
    pass


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
        except httpx.ReadTimeout as e:
            raise OllamaTimeout() from e
        if resp.status_code >= 500:
            self.known_down = True
            raise OllamaDown()
        resp.raise_for_status()
        self.known_down = False
        return resp.json()["message"]["content"]

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

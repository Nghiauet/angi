FROM python:3.12-slim-bookworm AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --format=requirements-txt > requirements.txt \
 && uv pip install --system --compile-bytecode -r requirements.txt
COPY src ./src
RUN uv pip install --system --no-deps .

FROM base AS final
# wget is required by the docker-compose healthcheck
RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
USER app
# 127.0.0.1 on purpose: the container runs with network_mode: host (see compose).
CMD ["uvicorn", "angi.main:app", "--host", "127.0.0.1", "--port", "46405"]

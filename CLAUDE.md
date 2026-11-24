# angi — Hôm nay ăn gì?

Sassy AI lunch decider for Vietnamese office workers. Server picks a dish from a
curated catalog; the local LLM writes ONE cà-khịa line with escalating attitude as
the user rejects dishes. Public at `https://angi.wakeuplate.io.vn/`.

## Build / run commands

```bash
uv sync                                   # install deps
uv run pytest                             # unit tests (Ollama mocked, weather disabled)
uv run python scripts/preview_lines.py    # persona tuning harness (needs live Ollama)
uv run uvicorn angi.main:app --host 127.0.0.1 --port 46495 --reload   # dev server (46405 is the live container)
docker compose up -d --build              # production container
bash scripts/smoke.sh                     # live e2e test
```

## Architecture

```
Browser ──HTTPS──> Cloudflare tunnel ──> nginx 127.0.0.1:8691 (Host routing)
                                          └─> uvicorn 127.0.0.1:46405 (network_mode: host)
                                                ├─ StaticFiles → static/ (single page)
                                                └─ POST /api/suggest
                                                     → weather (open-meteo, cached 30m)
                                                     → picker (server picks dish, LLM never does)
                                                     → GpuGate → Ollama one-liner (temp 0.8)
                                                     → validate → canned floor on ANY failure
```

Core principle: **the app never breaks**. Ollama down/slow/queue-full or bad output
→ canned line from `lines.py` pools (`fallback: true`). Worst case it's a random
wheel with attitude.

- `src/angi/dishes.py` + `src/angi/data/dishes.json` — ~170 dishes, quota-tested (tiers/categories;
  ≥12 tier-1 noodles so budget-20k mode isn't bread/snack-only).
- `src/angi/picker.py` — budget is HARD filter; weather/delivery soft, relaxed in order.
- `src/angi/lines.py` — sass_tier (0-5 by rejection count: 3=roast at 5-7, 4=resigned-
  philosophical at 8-14, 5=absurdist admiration at 15+), output validation (banned words,
  CJK code-switch, glued English, wrong-dish scan), canned pools per tier + RAIN/HOT overlays.
- `src/angi/prompts.py` — persona + 12 golden few-shots incl. anti-drift shots (foreign
  dish names in dish AND rejected-hint → answer stays Vietnamese). THE tuning surface:
  bad line class in logs → add a shot here, verify with scripts/preview_lines.py
  (≥90% single-shot bar; production adds a retry → ~96% effective).
- `src/angi/api.py` — after a validation reject, ONE retry at temperature 0.6 (status
  `ok_retry`, counts as success) before falling to canned (`canned_reject`). Other
  canned statuses: `canned_queue` (GPU queue full), `canned_down`, `canned_timeout`
  (incl. the 20 s total deadline), `canned_error` (Ollama 4xx / bad body / anything
  unexpected), `canned_busy` (global LLM budget used up). Only catalog dish names from
  `rejected` reach the prompt (prompt-injection guard in `prompts.build_messages`).
- `src/angi/weather.py` — open-meteo HN/SG, silent degrade to "any"; `current_full`
  also returns temp_c for the `/api/weather` chip badge.

## API

- `GET /health` → `{"status":"ok"}`.
- `POST /api/suggest` `{budget: "20"|"50"|"max"|null, mood: "vui"|"met"|"deadline"|null,
  city: "hn"|"sg"|null, rejected: [names], client_date: "YYYY-MM-DD"}` (wrong-typed
  enums are treated as null; the 30 most recent `rejected` names are used) →
  `{dish, line, tier: 0-5, fallback, price_tier, category, weather, broke}`.
  Always 200 for valid input. 400 malformed shape; 413 body > 64 KB; 415 unless
  `Content-Type: application/json` (blocks cross-site simple POSTs); 429 only rate limiter
  (20 req/min per visitor, keyed on CF-Connecting-IP, IPv6 per /64 — nginx's
  X-Real-IP is always 127.0.0.1 here, cloudflared is local). Broke mode: day >= 25
  + budget "20" → mì tôm jokes.
- `GET /api/weather?city=hn|sg` → `{weather, temp_c}` (cached, never GPU; 400 bad city).

Frontend game layer (all client-side, localStorage): achievement badges at 10/20/30
rejections (shown on card + share card), mascot face per tier 😋😏😤🙄😮‍💨🫡,
victory line + consecutive-day "chốt" streak, city-chip pulse until first pick.

## Tech stack

Python 3.11+/FastAPI/httpx/pydantic-settings, uv, vanilla JS frontend (canvas share
card, localStorage daily session), Docker multi-stage uv build, host Ollama
`qwen2.5:7b-instruct-q4_K_M` at **temperature 0.8** (0.9 caused Chinese code-switching).

## Server-specific notes

Deployment and ops notes for the server this runs on live in `CLAUDE.local.md`
(machine-local, listed in `.git/info/exclude`, never committed).

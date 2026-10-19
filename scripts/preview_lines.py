"""Persona tuning harness (dev only): run sample contexts through the real
prompt + live Ollama + validation, print the results for human judgment.

Usage: uv run python scripts/preview_lines.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx  # noqa: E402

from angi.config import settings  # noqa: E402
from angi.lines import sanitize, validate  # noqa: E402
from angi.ollama_client import OllamaClient  # noqa: E402
from angi.prompts import build_messages  # noqa: E402

CONTEXTS = [
    dict(dish="Bún riêu cua", tier=0, budget="50", mood=None, weather="any", rejected=[], broke=False),
    dict(dish="Cơm tấm sườn bì chả", tier=0, budget=None, mood="vui", weather="hot", rejected=[], broke=False),
    dict(dish="Phở bò", tier=0, budget="max", mood="met", weather="rain", rejected=[], broke=False),
    dict(dish="Bánh mì ốp la", tier=1, budget="20", mood=None, weather="any", rejected=["Xôi xéo"], broke=False),
    dict(dish="Bún chả", tier=1, budget="50", mood="deadline", weather="any", rejected=["Phở gà", "Cơm văn phòng"], broke=False),
    dict(dish="Gỏi cuốn tôm thịt", tier=1, budget="20", mood="vui", weather="hot", rejected=["Bún bò Huế"], broke=False),
    dict(dish="Cháo sườn", tier=2, budget="20", mood="met", weather="rain", rejected=["Phở bò", "Bún riêu cua", "Miến gà"], broke=False),
    dict(dish="Cơm gà xối mỡ", tier=2, budget="50", mood="deadline", weather="rain", rejected=["Bún chả", "Phở bò", "Cơm tấm sườn bì chả", "Bánh mì chảo"], broke=False),
    dict(dish="Hủ tiếu Nam Vang", tier=2, budget=None, mood=None, weather="any", rejected=["Cơm văn phòng", "Bún thang", "Mì vằn thắn"], broke=False),
    dict(dish="Bánh mì thịt nướng", tier=3, budget="max", mood=None, weather="any", rejected=["a"] * 6, broke=False),
    dict(dish="Phở bò", tier=3, budget="50", mood="met", weather="rain", rejected=["a"] * 7, broke=False),
    dict(dish="Cơm rang dưa bò", tier=3, budget="20", mood="deadline", weather="any", rejected=["a"] * 7, broke=False),
    dict(dish="Mì tôm trứng", tier=1, budget="20", mood="met", weather="any", rejected=["Cơm bụi bình dân"], broke=True),
    dict(dish="Cháo gà", tier=2, budget="20", mood=None, weather="rain", rejected=["a"] * 4, broke=True),
    dict(dish="Xôi xéo", tier=0, budget="20", mood=None, weather="any", rejected=[], broke=True),
    dict(dish="Salad ức gà", tier=0, budget="50", mood="vui", weather="hot", rejected=[], broke=False),
    dict(dish="Bún đậu mắm tôm", tier=1, budget="50", mood="vui", weather="hot", rejected=["Bún ốc"], broke=False),
    dict(dish="Ramen Nhật", tier=0, budget="max", mood="met", weather="rain", rejected=[], broke=False),
    dict(dish="Lẩu Thái mini", tier=2, budget="max", mood="vui", weather="rain", rejected=["a"] * 3, broke=False),
    dict(dish="Bánh xèo", tier=4, budget=None, mood="vui", weather="any", rejected=["a"] * 8, broke=False),
    # --- tier 4/5 deep sessions + the exact foreign-name shapes that caused
    # production language drift (CJK / glued English) ---
    dict(dish="Bún mọc", tier=4, budget="max", mood="vui", weather="any",
         rejected=["a"] * 7 + ["Smoothie bowl", "Súp cua", "Ramen Nhật"], broke=False),
    dict(dish="Cháo sườn", tier=4, budget="20", mood="met", weather="rain", rejected=["a"] * 12, broke=False),
    dict(dish="Cơm văn phòng", tier=5, budget=None, mood="deadline", weather="any", rejected=["a"] * 16, broke=False),
    dict(dish="Cơm gà teriyaki", tier=5, budget="max", mood="vui", weather="any",
         rejected=["a"] * 18 + ["Pad Thái tôm", "Udon xào bò", "Pizza hải sản"], broke=False),
    dict(dish="Cơm trộn Hàn Quốc", tier=5, budget="max", mood="vui", weather="any", rejected=["a"] * 30, broke=False),
    dict(dish="Pad Thái tôm", tier=3, budget="max", mood="vui", weather="any",
         rejected=["a"] * 4 + ["Smoothie bowl", "Súp cua"], broke=False),
    dict(dish="Soba lạnh", tier=1, budget="max", mood=None, weather="hot", rejected=["Bún cá"], broke=False),
    dict(dish="Takoyaki", tier=2, budget="50", mood="vui", weather="any", rejected=["a"] * 4, broke=False),
]


async def main() -> None:
    async with httpx.AsyncClient(
        base_url=settings.ollama_url,
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
    ) as http:
        ollama = OllamaClient(http)
        ok = 0
        for i, ctx in enumerate(CONTEXTS):
            raw = await ollama.complete(build_messages(**ctx))
            line = validate(sanitize(raw), ctx["dish"])
            status = "OK    " if line else "REJECT"
            if line:
                ok += 1
            print(f"[{i:2}] tier={ctx['tier']} {status} | {ctx['dish']}")
            print(f"     -> {line or sanitize(raw)[:160]}")
        print(f"\n{ok}/{len(CONTEXTS)} passed validation ({ok / len(CONTEXTS):.0%})")


if __name__ == "__main__":
    asyncio.run(main())

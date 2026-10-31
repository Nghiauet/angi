import json
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator

_DATA_FILE = Path(__file__).parent / "data" / "dishes.json"


class Dish(BaseModel):
    name: str
    price_tier: Literal[1, 2, 3]
    speed: Literal["fast", "slow"]
    weather_fit: Literal["rain", "hot", "any"]
    delivery_friendly: bool
    category: Literal["noodle", "rice", "bread", "veg", "snack"]
    region_note: Literal["Bắc", "Trung", "Nam"] | None

    @field_validator("name")
    @classmethod
    def name_length(cls, v: str) -> str:
        if not v or len(v) > 50:
            raise ValueError("dish name must be 1-50 chars")
        return v


def fold_name(name: str) -> str:
    """Diacritic- and case-insensitive key for matching rejected names."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.replace("đ", "d").replace("Đ", "D").lower().split())


def _load() -> list[Dish]:
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    dishes = [Dish(**d) for d in raw["dishes"]]
    folded = [fold_name(d.name) for d in dishes]
    if len(set(folded)) != len(folded):
        dupes = {f for f in folded if folded.count(f) > 1}
        raise ValueError(f"duplicate dish names: {dupes}")
    return dishes


# Loaded once at import; bad data must crash startup loudly, never ship.
DISHES: list[Dish] = _load()
NAMES_FOLDED: set[str] = {fold_name(d.name) for d in DISHES}
_CANONICAL: dict[str, str] = {fold_name(d.name): d.name for d in DISHES}


def catalog_name(name: str) -> str | None:
    """The catalog's spelling of `name`, or None if it is not a catalog dish."""
    return _CANONICAL.get(fold_name(name))

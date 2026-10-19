import random

from .dishes import DISHES, Dish, fold_name

_BUDGET_TIERS = {"20": {1}, "50": {1, 2}}
_MIN_POOL = 5


def pick(budget: str | None, weather: str, rejected: list[str]) -> Dish:
    """Filtered random pick. Budget is a HARD constraint; weather/delivery are
    soft constraints relaxed in order until the pool is big enough. If the user
    rejected everything, rejections are forgiven — tier-3 sass handles them."""
    tiers = _BUDGET_TIERS.get(budget or "", {1, 2, 3})
    budget_pool = [d for d in DISHES if d.price_tier in tiers]

    rejected_folded = {fold_name(r) for r in rejected}
    pool = [d for d in budget_pool if fold_name(d.name) not in rejected_folded]
    if not pool:
        pool = budget_pool  # rejected everything -> forgive

    candidates = _weather_filter(pool, weather)
    return random.choice(candidates)


def _weather_filter(pool: list[Dish], weather: str) -> list[Dish]:
    if weather == "rain":
        strict = [d for d in pool if d.weather_fit in ("rain", "any") and d.delivery_friendly]
        if len(strict) >= _MIN_POOL:
            return strict
        loose = [d for d in pool if d.weather_fit in ("rain", "any")]
        if len(loose) >= _MIN_POOL:
            return loose
    elif weather == "hot":
        loose = [d for d in pool if d.weather_fit in ("hot", "any")]
        if len(loose) >= _MIN_POOL:
            return loose
    return pool

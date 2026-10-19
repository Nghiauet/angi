from angi.dishes import DISHES
from angi.picker import pick


def test_budget_is_hard_constraint():
    for _ in range(50):
        assert pick("20", "any", []).price_tier == 1
    for _ in range(50):
        assert pick("50", "any", []).price_tier in (1, 2)


def test_rejected_excluded():
    rejected = ["Phở bò", "pho bo", "Bún chả"]  # folded matching
    for _ in range(100):
        d = pick(None, "any", rejected)
        assert d.name not in ("Phở bò", "Bún chả")


def test_reject_everything_forgives():
    all_names = [d.name for d in DISHES]
    d = pick(None, "any", all_names)
    assert d is not None  # falls back to the full pool


def test_rain_prefers_delivery():
    for _ in range(100):
        d = pick(None, "rain", [])
        assert d.weather_fit in ("rain", "any")


def test_hot_avoids_rain_comfort():
    for _ in range(100):
        d = pick(None, "hot", [])
        assert d.weather_fit in ("hot", "any")


def test_unknown_budget_means_all():
    tiers = {pick("bogus", "any", []).price_tier for _ in range(200)}
    assert 3 in tiers  # tier 3 reachable when budget is not restrictive

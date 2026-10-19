from collections import Counter

from angi.dishes import DISHES, fold_name


def test_catalog_size():
    assert len(DISHES) >= 165


def test_tier_quotas():
    tiers = Counter(d.price_tier for d in DISHES)
    assert tiers[1] >= 65, tiers
    assert tiers[2] >= 70, tiers
    assert tiers[3] >= 25, tiers


def test_category_quotas():
    cats = Counter(d.category for d in DISHES)
    assert cats["noodle"] >= 50, cats
    assert cats["rice"] >= 45, cats
    assert cats["bread"] >= 16, cats
    assert cats["veg"] >= 16, cats
    assert cats["snack"] >= 30, cats


def test_budget_pools_survive_rejections():
    # every budget filter must yield >= 40 dishes so deep reroll sessions
    # (production record: 30 rejections) never exhaust it
    for tiers in ({1}, {1, 2}, {1, 2, 3}):
        pool = [d for d in DISHES if d.price_tier in tiers]
        assert len(pool) >= 40, tiers


def test_budget_noodles_not_starved():
    # the 20k pool used to be bread/snack heavy — keep real noodles in it
    noodles_t1 = [d for d in DISHES if d.price_tier == 1 and d.category == "noodle"]
    assert len(noodles_t1) >= 12, len(noodles_t1)


def test_names_unique_folded():
    folded = [fold_name(d.name) for d in DISHES]
    assert len(set(folded)) == len(folded)


def test_broke_staples_present():
    names = {fold_name(d.name) for d in DISHES}
    assert fold_name("Mì tôm trứng") in names

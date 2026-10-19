from angi.lines import (
    CANNED,
    CANNED_BROKE,
    CANNED_HOT,
    CANNED_RAIN,
    canned_line,
    sanitize,
    sass_tier,
    validate,
)


def test_sass_tier_boundaries():
    assert sass_tier(0) == 0
    assert sass_tier(1) == 1
    assert sass_tier(2) == 1
    assert sass_tier(3) == 2
    assert sass_tier(4) == 2
    assert sass_tier(5) == 3
    assert sass_tier(7) == 3
    assert sass_tier(8) == 4
    assert sass_tier(14) == 4
    assert sass_tier(15) == 5
    assert sass_tier(30) == 5


def test_sanitize():
    assert sanitize('"Ăn phở đi bạn ơi."') == "Ăn phở đi bạn ơi."
    assert sanitize("Đây là câu trả lời:\nĂn phở đi.") == "Ăn phở đi."
    assert sanitize("```\nĂn phở đi.\n```") == "Ăn phở đi."
    assert sanitize("- Ăn phở đi.") == "Ăn phở đi."
    # multi-line -> first line only
    assert sanitize("Ăn phở đi.\nGiải thích: vì ngon.") == "Ăn phở đi."


def test_validate_accepts_good_line():
    line = "Trời mưa mà đòi bún đậu? Ngồi yên đó, ship cơm gà xối mỡ về."
    assert validate(line, "Cơm gà xối mỡ") == line


def test_validate_rejects_banned():
    assert validate("Món này vcl luôn, ăn Phở bò đi.", "Phở bò") is None
    assert validate("Nghèo kiết thế thì ăn Phở bò đi.", "Phở bò") is None


def test_validate_rejects_english():
    assert validate("You should really eat this dish today my friend", "Phở bò") is None


def test_validate_rejects_cjk_code_switch():
    assert validate("Mưa như trút… 喝一碗暖和的鸡汤吧，Phở bò nhé。", "Phở bò") is None


def test_validate_rejects_glued_english():
    assert validate("Xôi xéo ngon mà, còn gìBetter pick này.", "Xôi xéo") is None


def test_validate_rejects_too_long():
    assert validate("ơ " * 150, "Phở bò") is None
    assert validate("", "Phở bò") is None


def test_validate_wrong_dish():
    # line talks about a different catalog dish -> reject
    assert validate("Thôi đừng ăn thế, làm bát bún chả cho nóng.", "Phở bò") is None
    # mentioning the right dish is fine even if folded name appears
    assert validate("Phở bò nóng hổi đây, chốt nhé!", "Phở bò") is not None


def test_canned_pools_complete():
    for tier in (0, 1, 2, 3, 4, 5):
        assert len(CANNED[tier]) >= 8
        for template in CANNED[tier]:
            line = template.format(dish="Phở bò")
            assert len(line) <= 160
            assert "Phở bò" in line
    for pool in (CANNED_BROKE, CANNED_RAIN, CANNED_HOT):
        assert len(pool) >= 4
        for template in pool:
            line = template.format(dish="Mì tôm trứng")
            assert len(line) <= 160
            assert "Mì tôm trứng" in line


def test_canned_pools_pass_own_validation():
    # a canned line must never trip the validator's content rules
    for tier in (0, 1, 2, 3, 4, 5):
        for template in CANNED[tier]:
            assert validate(template.format(dish="Phở bò"), "Phở bò") is not None


def test_canned_line_renders():
    line = canned_line(5, "Bánh mì thịt nướng")
    assert "Bánh mì thịt nướng" in line


def test_canned_line_weather_pools():
    # with weather forced, the rain/hot overlays must appear at least sometimes
    rain_lines = {canned_line(0, "Phở bò", weather="rain") for _ in range(200)}
    assert any(t.format(dish="Phở bò") in rain_lines for t in CANNED_RAIN)
    hot_lines = {canned_line(0, "Phở bò", weather="hot") for _ in range(200)}
    assert any(t.format(dish="Phở bò") in hot_lines for t in CANNED_HOT)

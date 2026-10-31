import json
from pathlib import Path

from angi.config import settings
from angi.ratelimit import SlidingWindow


def ok_line(messages):
    dish = messages[-1]["content"].split("Món: ")[1].split(".")[0]
    return f"Trưa nay {dish} là chân ái, chốt nhé bạn ơi!"


def test_sliding_window_limits_and_recovers():
    w = SlidingWindow(2, 60.0)
    assert w.allow("a", now=0) and w.allow("a", now=1)
    assert not w.allow("a", now=2)
    assert w.allow("a", now=61)  # first hit left the window


def test_prune_drops_idle_keys():
    # old _prune kept every key ever seen (deques only shrink when their own
    # key returns), so the dict grew by one entry per visitor until restart
    w = SlidingWindow(5, 60.0)
    for i in range(150):
        w.allow(f"old-{i}", now=0.0)
    for i in range(100):
        w.allow(f"new-{i}", now=100.0)
    assert not any(k.startswith("old-") for k in w.hits)
    assert len(w.hits) <= 100


def test_limit_is_per_visitor_not_per_proxy(make_client):
    # nginx sets X-Real-IP to 127.0.0.1 for everyone (cloudflared is local);
    # CF-Connecting-IP is the visitor
    _, client = make_client(ok_line)
    proxy = {"X-Real-IP": "127.0.0.1"}
    for _ in range(settings.rate_rpm):
        r = client.post("/api/suggest", json={}, headers={**proxy, "CF-Connecting-IP": "203.0.113.7"})
        assert r.status_code == 200
    r = client.post("/api/suggest", json={}, headers={**proxy, "CF-Connecting-IP": "203.0.113.7"})
    assert r.status_code == 429
    r = client.post("/api/suggest", json={}, headers={**proxy, "CF-Connecting-IP": "198.51.100.9"})
    assert r.status_code == 200  # a second visitor is not blocked by the first


def test_ipv6_visitors_share_a_bucket_per_64(make_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_rpm", 2)
    _, client = make_client(ok_line)
    for host in ("2001:db8:1:2::1", "2001:db8:1:2::abcd"):
        assert client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": host}).status_code == 200
    r = client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": "2001:db8:1:2:ffff::9"})
    assert r.status_code == 429
    r = client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": "2001:db8:1:3::1"})
    assert r.status_code == 200


def test_falls_back_to_x_real_ip_then_socket(make_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_rpm", 1)
    _, client = make_client(ok_line)
    assert client.post("/api/suggest", json={}, headers={"X-Real-IP": "192.0.2.1"}).status_code == 200
    assert client.post("/api/suggest", json={}, headers={"X-Real-IP": "192.0.2.1"}).status_code == 429
    assert client.post("/api/suggest", json={}).status_code == 200  # socket peer "testclient"


def test_global_llm_budget_serves_canned_lines(make_client, monkeypatch):
    monkeypatch.setattr(settings, "llm_rpm_global", 2)
    calls = []

    def counting(messages):
        calls.append(1)
        return ok_line(messages)

    _, client = make_client(counting)
    results = [
        client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": f"192.0.2.{i}"}).json()
        for i in range(4)
    ]
    assert len(calls) == 2  # GPU used only within the budget
    assert [r["fallback"] for r in results] == [False, False, True, True]
    assert all(r["dish"] in r["line"] for r in results)
    statuses = [json.loads(ln)["status"] for ln in Path(settings.usage_file).read_text().splitlines()]
    assert statuses == ["ok", "ok", "canned_busy", "canned_busy"]


def test_ipv4_mapped_ipv6_is_the_ipv4_visitor(make_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_rpm", 1)
    _, client = make_client(ok_line)
    assert client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": "192.0.2.5"}).status_code == 200
    r = client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": "::ffff:192.0.2.5"})
    assert r.status_code == 429


def test_garbage_ip_header_does_not_crash(make_client):
    _, client = make_client(ok_line)
    for value in ("not-an-ip", " ", "1.2.3.4, 5.6.7.8", "x" * 500):
        assert client.post("/api/suggest", json={}, headers={"CF-Connecting-IP": value}).status_code == 200

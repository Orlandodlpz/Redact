"""Demo gate tests: the passcode, the per IP limit, the day cap, and the address.

The gate's whole job is to stop one person spending the credits the demo needs on
judging day, so the cases that matter are the ones where somebody is trying.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.config import Settings, get_settings
from app.demo_gate import DAY_S, HOUR_S, PASSCODE_HEADER, DemoGate
from app.schemas import AnalyzeResponse

PASSCODE = "open-sesame-2026"


def settings(**over) -> Settings:
    base = {"meta_api_key": "test-key-not-real", "demo_passcode": PASSCODE,
            "rate_limit_per_ip_per_hour": 3, "daily_analyze_cap": 5}
    return Settings(**{**base, **over})


def gate(**over) -> DemoGate:
    return DemoGate(settings(**over))


# --- passcode -----------------------------------------------------------------


def test_the_right_passcode_gets_in():
    assert gate().check("/analyze", PASSCODE, "1.2.3.4").allowed


@pytest.mark.parametrize("given", [None, "", "wrong", PASSCODE + "x", PASSCODE.upper()])
def test_anything_else_does_not(given):
    d = gate().check("/analyze", given, "1.2.3.4")
    assert not d.allowed and d.status == 401


def test_a_missing_and_a_wrong_passcode_look_identical():
    """Different messages would tell a guesser which half they got right."""
    missing = gate().check("/analyze", None, "1.2.3.4")
    wrong = gate().check("/analyze", "nope", "1.2.3.4")
    assert (missing.status, missing.detail) == (wrong.status, wrong.detail)


def test_no_passcode_configured_means_no_gate():
    """Local development runs without one. The deploy sets it."""
    assert gate(demo_passcode=None).check("/analyze", None, "1.2.3.4").allowed


def test_health_is_never_gated():
    """The hosting platform calls it to decide whether the service is alive."""
    assert gate().check("/health", None, "1.2.3.4").allowed


def test_export_needs_the_passcode_too():
    assert not gate().check("/export", None, "1.2.3.4").allowed
    assert gate().check("/export", PASSCODE, "1.2.3.4").allowed


# --- per IP limit -------------------------------------------------------------


def test_an_ip_gets_its_allowance_then_waits():
    g = gate()
    for _ in range(3):
        assert g.check("/analyze", PASSCODE, "1.2.3.4", now=100).allowed
        g.record("/analyze", "1.2.3.4", now=100)
    blocked = g.check("/analyze", PASSCODE, "1.2.3.4", now=100)
    assert not blocked.allowed and blocked.status == 429
    assert blocked.retry_after_s and blocked.retry_after_s <= HOUR_S


def test_one_busy_ip_does_not_block_anybody_else():
    g = gate()
    for _ in range(3):
        g.record("/analyze", "1.2.3.4", now=100)
    assert not g.check("/analyze", PASSCODE, "1.2.3.4", now=100).allowed
    assert g.check("/analyze", PASSCODE, "5.6.7.8", now=100).allowed


def test_the_window_reopens_after_an_hour():
    g = gate()
    for _ in range(3):
        g.record("/analyze", "1.2.3.4", now=100)
    assert not g.check("/analyze", PASSCODE, "1.2.3.4", now=100).allowed
    assert g.check("/analyze", PASSCODE, "1.2.3.4", now=100 + HOUR_S + 1).allowed


def test_only_analyze_counts_against_the_limit():
    """Export runs no model, so it costs nothing and should not use up an allowance."""
    g = gate()
    for _ in range(20):
        assert g.check("/export", PASSCODE, "1.2.3.4", now=100).allowed
        g.record("/export", "1.2.3.4", now=100)
    assert g.check("/analyze", PASSCODE, "1.2.3.4", now=100).allowed


# --- day cap ------------------------------------------------------------------


def test_the_day_cap_holds_even_across_many_addresses():
    """The per IP limit does nothing against a handful of addresses. This is the
    number that bounds the bill."""
    g = gate()
    for n in range(5):
        ip = f"10.0.0.{n}"
        assert g.check("/analyze", PASSCODE, ip, now=100).allowed
        g.record("/analyze", ip, now=100)
    blocked = g.check("/analyze", PASSCODE, "10.0.0.99", now=100)
    assert not blocked.allowed and blocked.status == 503
    assert blocked.retry_after_s and blocked.retry_after_s <= DAY_S


def test_the_day_cap_resets_the_next_day():
    g = gate()
    for n in range(5):
        g.record("/analyze", f"10.0.0.{n}", now=100)
    assert not g.check("/analyze", PASSCODE, "10.0.0.99", now=100).allowed
    assert g.check("/analyze", PASSCODE, "10.0.0.99", now=100 + DAY_S + 1).allowed


# --- which address ------------------------------------------------------------


def test_the_forwarded_header_is_ignored_unless_the_deploy_trusts_it():
    """Off a proxy, that header is whatever the caller typed. Trusting it would hand
    out a fresh allowance per request."""
    g = gate(trust_proxy_header=False)
    assert g.client_ip("9.9.9.9", "1.2.3.4") == "1.2.3.4"


def test_behind_a_proxy_the_forwarded_header_is_the_only_real_address():
    """The socket address is the proxy's, so every visitor would share one bucket."""
    g = gate(trust_proxy_header=True)
    assert g.client_ip("9.9.9.9", "1.2.3.4") == "9.9.9.9"
    assert g.client_ip("9.9.9.9, 10.0.0.1, 10.0.0.2", "1.2.3.4") == "9.9.9.9"


def test_an_unknown_address_still_gets_a_bucket():
    g = gate(trust_proxy_header=True)
    assert g.client_ip(None, None) == "unknown"
    assert g.client_ip("", None) == "unknown"


def test_spoofing_the_header_does_not_reset_the_limit_when_it_is_not_trusted():
    g = gate(trust_proxy_header=False)
    for n in range(3):
        ip = g.client_ip(f"8.8.8.{n}", "1.2.3.4")
        g.record("/analyze", ip, now=100)
    ip = g.client_ip("8.8.8.99", "1.2.3.4")
    assert not g.check("/analyze", PASSCODE, ip, now=100).allowed


# --- through the app ----------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DEMO_PASSCODE", PASSCODE)
    monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_HOUR", "2")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    get_settings.cache_clear()

    async def fake_analyze(image_bytes, destination, *, client=None):
        return AnalyzeResponse(
            image_id="abc", width=10, height=10, destination=destination, findings=[],
            judge_status="ok", prompt_version="judge_v1", model_ids={}, timings_ms={},
            est_cost_usd=0.0)

    monkeypatch.setattr(main, "analyze", fake_analyze)
    monkeypatch.setattr(main, "MetaClient", lambda settings: _FakeClient())
    with TestClient(main.create_app()) as c:
        yield c
    get_settings.cache_clear()


class _FakeClient:
    async def close(self):
        pass


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def upload():
    return {"image": ("p.png", io.BytesIO(png()), "image/png")}


def test_the_app_refuses_without_the_passcode(client):
    r = client.post("/analyze", files=upload(), data={"destination": "public"})
    assert r.status_code == 401
    assert r.headers["cache-control"] == "no-store"


def test_the_app_serves_with_it(client):
    r = client.post("/analyze", files=upload(), data={"destination": "public"},
                    headers={PASSCODE_HEADER: PASSCODE})
    assert r.status_code == 200


def test_health_still_answers_without_a_passcode(client):
    assert client.get("/health").status_code == 200


def test_the_app_enforces_the_limit_and_says_when_to_come_back(client):
    head = {PASSCODE_HEADER: PASSCODE}
    for _ in range(2):
        assert client.post("/analyze", files=upload(),
                           data={"destination": "public"}, headers=head).status_code == 200
    r = client.post("/analyze", files=upload(), data={"destination": "public"}, headers=head)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert json.loads(r.content)["detail"]


def test_a_refused_request_does_not_use_up_an_allowance(client):
    """A missing destination is a 422 that runs no model, so it costs nothing."""
    head = {PASSCODE_HEADER: PASSCODE}
    for _ in range(5):
        assert client.post("/analyze", files=upload(), headers=head).status_code == 422
    assert client.post("/analyze", files=upload(),
                       data={"destination": "public"}, headers=head).status_code == 200


def test_a_refused_request_still_carries_cors_headers(client):
    """The gate answers a bad passcode itself, from a middleware. Built outside CORS
    that response has no Access-Control-Allow-Origin, so a judge who mistypes the
    passcode sees a CORS error rather than being told to check the passcode."""
    origin = "http://localhost:3000"
    r = client.post("/analyze", files=upload(), data={"destination": "public"},
                    headers={"origin": origin})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == origin
    assert json.loads(r.content)["detail"] == "This demo needs a passcode."


def test_a_rate_limited_request_still_carries_cors_headers(client):
    origin = "http://localhost:3000"
    head = {PASSCODE_HEADER: PASSCODE, "origin": origin}
    for _ in range(2):
        client.post("/analyze", files=upload(), data={"destination": "public"},
                    headers=head)
    r = client.post("/analyze", files=upload(), data={"destination": "public"},
                    headers=head)
    assert r.status_code == 429
    assert r.headers.get("access-control-allow-origin") == origin


def test_an_oversize_refusal_still_carries_cors_headers(client):
    origin = "http://localhost:3000"
    r = client.post("/analyze", content=b"", headers={
        "origin": origin, "content-length": str(100 * 1024 * 1024),
        "content-type": "application/octet-stream"})
    assert r.status_code == 413
    assert r.headers.get("access-control-allow-origin") == origin


def test_the_passcode_is_never_asked_for_in_a_url(client):
    """It goes in a header. Query strings end up in access logs at every hop."""
    r = client.post(f"/analyze?passcode={PASSCODE}", files=upload(),
                    data={"destination": "public"})
    assert r.status_code == 401


# --- the empty passcode footgun ----------------------------------------------


def test_an_empty_passcode_setting_means_no_gate_not_an_empty_gate():
    """`.env.example` ships `DEMO_PASSCODE=` with no value, which pydantic reads as "".

    Left alone that turns the gate on with a passcode of "", which refuses everyone who
    sends no header and admits anyone who sends an empty one. That is worse than no
    gate, because it looks like a gate.
    """
    s = Settings(meta_api_key="k", demo_passcode="")
    assert s.demo_passcode is None
    g = DemoGate(s)
    assert g.check("/analyze", None, "1.2.3.4").allowed
    assert g.check("/analyze", "", "1.2.3.4").allowed
    assert g.check("/analyze", "anything", "1.2.3.4").allowed


def test_an_empty_header_does_not_open_a_real_gate():
    assert not gate().check("/analyze", "", "1.2.3.4").allowed


def test_the_passcode_comparison_does_not_stop_at_the_first_wrong_character():
    """compare_digest, not ==. Not a realistic remote attack, but it is one line."""
    import inspect

    from app import demo_gate

    assert "compare_digest" in inspect.getsource(demo_gate.DemoGate.check)

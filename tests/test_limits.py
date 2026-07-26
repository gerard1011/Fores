"""Rate limiting, with particular attention to slot release.

A leaked concurrency slot is the failure mode that matters here: it is silent,
it survives every subsequent request, and it locks the caller out until the
process restarts. Several tests below exist only to pin that down.
"""

import anyio
import pytest

from api import config
from api.limits import Limiter, RateLimited


async def test_requests_under_the_limit_pass():
    lim = Limiter()
    for _ in range(5):
        await lim.check_rate("1.1.1.1", per_minute=5)


async def test_minute_limit_rejects_with_retry_after():
    lim = Limiter()
    for _ in range(5):
        await lim.check_rate("1.1.1.1", per_minute=5)

    with pytest.raises(RateLimited) as exc:
        await lim.check_rate("1.1.1.1", per_minute=5)

    assert exc.value.kind == "rate"
    assert 1 <= exc.value.retry_after <= 61


async def test_hour_limit_applies_independently_of_the_minute_limit():
    lim = Limiter()
    for _ in range(3):
        await lim.check_rate("1.1.1.1", per_minute=100, per_hour=3)

    with pytest.raises(RateLimited):
        await lim.check_rate("1.1.1.1", per_minute=100, per_hour=3)


async def test_limits_are_per_ip():
    lim = Limiter()
    for _ in range(5):
        await lim.check_rate("1.1.1.1", per_minute=5)

    await lim.check_rate("2.2.2.2", per_minute=5)


# --- concurrency ----------------------------------------------------------


async def test_concurrent_streams_per_ip_are_capped(monkeypatch):
    monkeypatch.setattr(config, "CHAT_STREAMS_PER_IP", 2)
    monkeypatch.setattr(config, "GLOBAL_INFLIGHT", 99)
    lim = Limiter()

    async with lim.chat_slot("1.1.1.1"), lim.chat_slot("1.1.1.1"):
        with pytest.raises(RateLimited) as exc:
            async with lim.chat_slot("1.1.1.1"):
                pass
        assert exc.value.kind == "concurrency"


async def test_global_cap_applies_across_different_ips(monkeypatch):
    monkeypatch.setattr(config, "CHAT_STREAMS_PER_IP", 99)
    monkeypatch.setattr(config, "GLOBAL_INFLIGHT", 2)
    lim = Limiter()

    async with lim.chat_slot("1.1.1.1"), lim.chat_slot("2.2.2.2"):
        # This is the guard that actually bounds spend: rotating IPs does not
        # get you past it.
        with pytest.raises(RateLimited) as exc:
            async with lim.chat_slot("3.3.3.3"):
                pass
        assert exc.value.kind == "capacity"


async def test_slot_is_released_on_normal_exit(monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_INFLIGHT", 1)
    lim = Limiter()

    async with lim.chat_slot("1.1.1.1"):
        pass
    async with lim.chat_slot("1.1.1.1"):
        pass

    assert lim.snapshot()["inflight"] == 0
    assert lim.snapshot()["active_ips"] == 0


async def test_slot_is_released_when_the_body_raises():
    lim = Limiter()

    with pytest.raises(ValueError):
        async with lim.chat_slot("1.1.1.1"):
            raise ValueError("mid-stream failure")

    assert lim.snapshot()["inflight"] == 0
    assert lim.snapshot()["active_ips"] == 0


async def test_slot_is_released_when_the_task_is_cancelled():
    """The client-disconnect path: cancellation, not a normal exception."""
    lim = Limiter()

    with anyio.move_on_after(0.05):
        async with lim.chat_slot("1.1.1.1"):
            await anyio.sleep_forever()

    assert lim.snapshot()["inflight"] == 0
    assert lim.snapshot()["active_ips"] == 0


async def test_rejected_per_ip_request_does_not_consume_a_global_slot(monkeypatch):
    monkeypatch.setattr(config, "CHAT_STREAMS_PER_IP", 1)
    monkeypatch.setattr(config, "GLOBAL_INFLIGHT", 5)
    lim = Limiter()

    async with lim.chat_slot("1.1.1.1"):
        with pytest.raises(RateLimited):
            async with lim.chat_slot("1.1.1.1"):
                pass
        # Both counters move together or not at all — a partial acquire would
        # bleed global capacity on every rejection.
        assert lim.snapshot()["inflight"] == 1


async def test_rejected_global_request_does_not_leave_a_per_ip_slot(monkeypatch):
    monkeypatch.setattr(config, "CHAT_STREAMS_PER_IP", 5)
    monkeypatch.setattr(config, "GLOBAL_INFLIGHT", 1)
    lim = Limiter()

    async with lim.chat_slot("1.1.1.1"):
        with pytest.raises(RateLimited):
            async with lim.chat_slot("2.2.2.2"):
                pass
        assert lim.snapshot()["active_ips"] == 1


async def test_rejections_are_counted():
    lim = Limiter()
    for _ in range(2):
        await lim.check_rate("1.1.1.1", per_minute=2)
    with pytest.raises(RateLimited):
        await lim.check_rate("1.1.1.1", per_minute=2)

    assert lim.snapshot()["rejections"]["rate"] == 1


# --- client identification ------------------------------------------------


async def test_forwarded_for_header_is_ignored(client, monkeypatch):
    """Trusting X-Forwarded-For with no proxy in front makes limits opt-out."""
    monkeypatch.setattr(config, "CENSUS_PER_MINUTE", 2)

    for _ in range(2):
        await client.get("/api/datasets/census/categories")

    resp = await client.get(
        "/api/datasets/census/categories",
        headers={"X-Forwarded-For": "9.9.9.9"},
    )
    assert resp.status_code == 429

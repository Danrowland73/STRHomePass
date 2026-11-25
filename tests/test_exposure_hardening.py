"""Hardening for a guest page that is reachable from the internet.

* Wrong guesses at a link address are budgeted per client IP, so a short custom
  slug cannot be found by trying words. Once the budget is spent, every lookup
  from that address is refused, so a later right guess cannot be told apart.
* Every request body is capped before it is read, so a huge body sent to a
  made-up link is cut off rather than held in memory.
"""
import time

from app import database as db
from app.body_limit import REQUEST_BODY_LIMIT
from app.routers.guest import UNKNOWN_SLUG_LIMITS_PER_IP

PER_MINUTE = UNKNOWN_SLUG_LIMITS_PER_IP[0][1]


async def _custom(slug="beach"):
    return await db.create_token(
        label="Cottage", slug=slug, entity_ids=["light.living_room"],
        expires_at=int(time.time()) + 3600, ip_allowlist=None,
    )


async def test_guessing_is_cut_off_and_a_later_hit_is_indistinguishable(client, test_db, mock_ha_client):
    await _custom("beach")
    misses = [(await client.get(f"/g/guess-{i}")).status_code for i in range(PER_MINUTE)]
    assert set(misses) == {410}
    # The budget is spent: the next miss and the right guess look the same.
    assert (await client.get("/g/guess-next")).status_code == 429
    assert (await client.get("/g/beach")).status_code == 429
    assert (await client.get("/g/beach/state")).status_code == 429


async def test_a_real_guest_never_spends_the_budget(client, test_db, mock_ha_client):
    await _custom("beach")
    for _ in range(PER_MINUTE * 2):
        assert (await client.get("/g/beach/state")).status_code == 200


async def test_the_budget_is_per_client_address(client, test_db, mock_ha_client):
    """A guesser behind one address does not lock out a guest at another.
    The test client is loopback, a trusted proxy, so X-Forwarded-For is believed."""
    await _custom("beach")
    for i in range(PER_MINUTE):
        await client.get(f"/g/guess-{i}", headers={"X-Forwarded-For": "203.0.113.9"})
    assert (await client.get("/g/beach", headers={"X-Forwarded-For": "203.0.113.9"})).status_code == 429
    assert (await client.get("/g/beach", headers={"X-Forwarded-For": "198.51.100.7"})).status_code == 200


async def test_huge_bodies_are_refused_before_the_link_is_looked_up(client, test_db, mock_ha_client):
    big = b"{" + b" " * REQUEST_BODY_LIMIT + b"}"
    r = await client.post("/g/made-up/command", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    # Chunked, with no Content-Length to check up front.
    async def chunks():
        for _ in range(REQUEST_BODY_LIMIT // 4096 + 2):
            yield b" " * 4096
    r = await client.post("/g/made-up/pin", content=chunks(),
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413


async def test_ordinary_bodies_still_work(client, test_db, mock_ha_client):
    await _custom("beach")
    r = await client.post("/g/beach/command", json={
        "entity_id": "light.living_room", "service": "light.turn_on", "data": {},
    })
    assert r.status_code == 200, r.text

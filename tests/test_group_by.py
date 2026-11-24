"""Per-link guest page layout: by type or by Home Assistant area.

group_by is the layout a link's guest page opens with ("type", the sections by
kind every link drew before, or "area", one section per HA area), and
guest_can_regroup is whether the guest may switch between them. The area
lookup itself (ha_client.get_area_map) is tested against a fake ws_command;
the browser side is in tests/test_group_by_js.py.

Real DB (migrated per test), real routing; only ha_client is mocked.
"""
import time
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app import database as db
from app import ha_client
from app.config import settings
from app.models import TokenCreateRequest, TokenUpdateEntitiesRequest

KEY = "k" * 40
HEADERS = {"X-API-Key": KEY}

AREAS = {
    "areas": {"kitchen": "Kitchen", "garden": "Garden", "attic": "Attic"},
    "entity_areas": {"light.living_room": "kitchen", "switch.fan": "garden",
                     "lock.shed": "attic"},
}


@pytest.fixture
def api_on():
    with patch.object(settings, "api_enabled", True), patch.object(settings, "api_token", KEY):
        yield


async def _token(slug="layout", **kwargs):
    kwargs.setdefault("expires_at", int(time.time()) + 86400)
    return await db.create_token(
        label="Cottage", slug=slug, entity_ids=["light.living_room", "switch.fan"],
        ip_allowlist=None, **kwargs,
    )


async def _row(token_id):
    return await db.get_token_by_id(token_id)


# ---------------------------------------------------------------------------
# Models and storage
# ---------------------------------------------------------------------------

def test_defaults_are_the_page_as_it_always_was():
    body = TokenCreateRequest(label="x", entity_ids=["light.a"], expires_in_seconds=60)
    assert body.group_by == "type"
    assert body.guest_can_regroup is True


@pytest.mark.parametrize("value", ["room", "", "AREA", 1])
def test_unknown_layouts_are_refused(value):
    with pytest.raises(ValidationError):
        TokenUpdateEntitiesRequest(entity_ids=["light.a"], group_by=value)


async def test_existing_tokens_read_as_type_with_the_switch(test_db):
    t = await _token()
    row = await _row(t["id"])
    assert row["group_by"] == "type"
    assert row["guest_can_regroup"] == 1


async def test_set_token_layout_keeps_fields_left_out(test_db):
    t = await _token(group_by="area", guest_can_regroup=False)
    await db.set_token_layout(t["id"], None, None)
    row = await _row(t["id"])
    assert (row["group_by"], row["guest_can_regroup"]) == ("area", 0)
    await db.set_token_layout(t["id"], "type", None)
    row = await _row(t["id"])
    assert (row["group_by"], row["guest_can_regroup"]) == ("type", 0)


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------

async def test_create_stores_and_returns_the_layout(client, admin_session):
    resp = await client.post("/admin/tokens", cookies=admin_session, json={
        "label": "Cottage", "entity_ids": ["light.living_room"], "expires_in_seconds": 3600,
        "group_by": "area", "guest_can_regroup": False,
    })
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["group_by"] == "area"
    assert body["guest_can_regroup"] is False


async def test_entity_edit_changes_the_layout_and_reloads_guests(
    client, admin_session, mock_ha_client,
):
    t = await _token()
    resp = await client.patch(f"/admin/tokens/{t['id']}/entities", cookies=admin_session, json={
        "entity_ids": ["light.living_room"], "group_by": "area",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["group_by"] == "area"
    assert resp.json()["guest_can_regroup"] is True
    mock_ha_client["broadcast_schedule_changed"].assert_awaited_once_with(t["id"])


async def test_entity_edit_without_a_layout_change_does_not_reload(
    client, admin_session, mock_ha_client,
):
    t = await _token(group_by="area")
    resp = await client.patch(f"/admin/tokens/{t['id']}/entities", cookies=admin_session, json={
        "entity_ids": ["light.living_room"], "group_by": "area", "guest_can_regroup": True,
    })
    assert resp.status_code == 200, resp.text
    mock_ha_client["broadcast_schedule_changed"].assert_not_awaited()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def test_api_patch_sets_the_layout(client, api_on, test_db, mock_ha_client):
    t = await _token()
    resp = await client.patch(f"/api/v1/tokens/{t['id']}", headers=HEADERS,
                              json={"guest_can_regroup": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["group_by"] == "type"
    assert resp.json()["guest_can_regroup"] is False
    mock_ha_client["broadcast_schedule_changed"].assert_awaited_once_with(t["id"])


async def test_api_patch_refuses_a_revoked_token(client, api_on, test_db):
    t = await _token()
    await db.revoke_token(t["id"])
    resp = await client.patch(f"/api/v1/tokens/{t['id']}", headers=HEADERS,
                              json={"group_by": "area"})
    assert resp.status_code == 400
    assert (await _row(t["id"]))["group_by"] == "type"


async def test_api_duplicate_copies_the_layout(client, api_on, test_db):
    t = await _token(group_by="area", guest_can_regroup=False)
    resp = await client.post(f"/api/v1/tokens/{t['id']}/duplicate", json={}, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    copy = resp.json()
    assert (copy["group_by"], copy["guest_can_regroup"]) == ("area", False)


# ---------------------------------------------------------------------------
# Guest /state
# ---------------------------------------------------------------------------

async def test_state_carries_only_this_links_areas(client, test_db, mock_ha_client):
    mock_ha_client["get_area_map"].return_value = AREAS
    await _token(slug="state-areas", group_by="area")
    resp = await client.get("/g/state-areas/state")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["group_by"] == "area"
    assert data["guest_can_regroup"] is True
    assert data["entity_areas"] == {"light.living_room": "kitchen", "switch.fan": "garden"}
    # The attic holds nothing on this link, so its name never reaches the guest.
    assert data["area_names"] == {"kitchen": "Kitchen", "garden": "Garden"}


async def test_state_without_readable_areas(client, test_db, mock_ha_client):
    await _token(slug="state-no-areas", group_by="area")
    data = (await client.get("/g/state-no-areas/state")).json()
    assert data["entity_areas"] == {}
    assert data["area_names"] is None


# ---------------------------------------------------------------------------
# ha_client.get_area_map
# ---------------------------------------------------------------------------

def _fake_ws(replies, calls):
    async def ws_command(command):
        calls.append(command["type"])
        reply = replies[command["type"]]
        if isinstance(reply, Exception):
            raise reply
        return reply
    return ws_command


REGISTRY = {
    "config/area_registry/list": [
        {"area_id": "kitchen", "name": "Kitchen"},
        {"area_id": "garden", "name": "Garden"},
    ],
    "config/device_registry/list": [
        {"id": "dev1", "area_id": "kitchen"},
        {"id": "dev2", "area_id": None},
    ],
    "config/entity_registry/list": [
        # The device's area, like most entities.
        {"entity_id": "light.a", "device_id": "dev1", "area_id": None},
        # Its own area wins over its device's.
        {"entity_id": "light.b", "device_id": "dev1", "area_id": "garden"},
        # No area anywhere.
        {"entity_id": "switch.c", "device_id": "dev2", "area_id": None},
        # An area that no longer exists is no area.
        {"entity_id": "switch.d", "device_id": None, "area_id": "gone"},
    ],
}


async def test_area_map_resolves_entity_then_device_area(monkeypatch):
    calls = []
    monkeypatch.setattr(ha_client, "ws_command", _fake_ws(REGISTRY, calls))
    result = await ha_client.get_area_map()
    assert result == {
        "areas": {"kitchen": "Kitchen", "garden": "Garden"},
        "entity_areas": {"light.a": "kitchen", "light.b": "garden"},
    }
    # Cached: a second read asks HA nothing.
    assert await ha_client.get_area_map() == result
    assert len(calls) == 3


async def test_area_map_failure_is_none_and_not_retried_at_once(monkeypatch):
    calls = []
    replies = dict(REGISTRY)
    replies["config/area_registry/list"] = ha_client.WSCommandError("nope", "unauthorized")
    monkeypatch.setattr(ha_client, "ws_command", _fake_ws(replies, calls))
    assert await ha_client.get_area_map() is None
    assert await ha_client.get_area_map() is None
    assert calls == ["config/area_registry/list"]
    # Once the TTL has passed it asks again.
    ha_client._area_cache_ts -= ha_client.REGISTRY_CACHE_TTL + 1
    monkeypatch.setattr(ha_client, "ws_command", _fake_ws(REGISTRY, calls))
    assert (await ha_client.get_area_map())["areas"]["kitchen"] == "Kitchen"

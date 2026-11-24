"""Per-link page style: the standard look, the guest's own phone's look, or a
forced iOS or Android look.

The device is detected in the guest's browser by static/skin.js, before the
page paints; that file's two pure functions are run in node here. The look
itself is static/skins.css, keyed off data-skin on <html>.
"""
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app import database as db
from app.config import settings
from app.models import TokenUpdateEntitiesRequest
from tests.test_group_by_js import DASH_SEED, _dashboard
from tests.test_picker_js import node

ROOT = Path(__file__).resolve().parent.parent
KEY = "k" * 40
HEADERS = {"X-API-Key": KEY}

IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
# iPadOS asks for desktop sites and says it is a Mac.
IPAD = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Safari/605.1.15")
ANDROID = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")
WINDOWS = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


@pytest.fixture
def api_on():
    with patch.object(settings, "api_enabled", True), patch.object(settings, "api_token", KEY):
        yield


async def _token(slug="styled", **kwargs):
    kwargs.setdefault("expires_at", int(time.time()) + 86400)
    return await db.create_token(
        label="Cottage", slug=slug, entity_ids=["light.living_room"], ip_allowlist=None, **kwargs,
    )


# ---------------------------------------------------------------------------
# Detection (static/skin.js)
# ---------------------------------------------------------------------------

def _skin_js(probe: str):
    script = (ROOT / "static" / "skin.js").read_text() + "\n" + probe
    proc = subprocess.run([node, "--input-type=module"], input=script,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(node is None, reason="node is not installed")
def test_os_detection():
    cases = [[IPHONE, 5], [IPAD, 5], [IPAD, 0], [ANDROID, 5], [WINDOWS, 0], ["", 0]]
    out = _skin_js(f"console.log(JSON.stringify({json.dumps(cases)}.map(([ua, t]) => detectGuestOS(ua, t))));")
    # A Mac without touch is a Mac.
    assert out == ["ios", "ios", "other", "android", "other", "other"]


@pytest.mark.skipif(node is None, reason="node is not installed")
def test_style_resolution():
    styles = ["standard", "device", "ios", "android", "bogus"]
    oses = ["ios", "android", "other"]
    out = _skin_js(f"""
    const out = {{}};
    for (const s of {json.dumps(styles)}) out[s] = {json.dumps(oses)}.map(os => resolvePageSkin(s, os));
    console.log(JSON.stringify(out));
    """)
    assert out == {
        "standard": ["standard", "standard", "standard"],
        "device": ["ios", "android", "standard"],
        "ios": ["ios", "ios", "ios"],
        "android": ["android", "android", "android"],
        "bogus": ["standard", "standard", "standard"],
    }


# ---------------------------------------------------------------------------
# Storage and APIs
# ---------------------------------------------------------------------------

async def test_existing_links_keep_the_standard_look(test_db):
    t = await _token()
    assert (await db.get_token_by_id(t["id"]))["page_style"] == "standard"


@pytest.mark.parametrize("value", ["apple", "", "iOS", None])
def test_unknown_styles_are_refused(value):
    if value is None:
        assert TokenUpdateEntitiesRequest(entity_ids=["light.a"], page_style=None).page_style is None
        return
    with pytest.raises(ValidationError):
        TokenUpdateEntitiesRequest(entity_ids=["light.a"], page_style=value)


async def test_dashboard_create_and_edit(client, admin_session, mock_ha_client):
    resp = await client.post("/admin/tokens", cookies=admin_session, json={
        "label": "Cottage", "entity_ids": ["light.living_room"], "expires_in_seconds": 3600,
        "page_style": "device",
    })
    assert resp.status_code in (200, 201), resp.text
    token = resp.json()
    assert token["page_style"] == "device"
    resp = await client.patch(f"/admin/tokens/{token['id']}/entities", cookies=admin_session,
                              json={"entity_ids": ["light.living_room"], "page_style": "android"})
    assert resp.json()["page_style"] == "android"
    mock_ha_client["broadcast_schedule_changed"].assert_awaited_once_with(token["id"])


async def test_api_patch_and_duplicate(client, api_on, test_db):
    t = await _token()
    resp = await client.patch(f"/api/v1/tokens/{t['id']}", headers=HEADERS, json={"page_style": "ios"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["page_style"] == "ios"
    resp = await client.post(f"/api/v1/tokens/{t['id']}/duplicate", json={}, headers=HEADERS)
    assert resp.json()["page_style"] == "ios"


# ---------------------------------------------------------------------------
# Guest page
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style", ["standard", "device", "ios", "android"])
async def test_guest_page_resolves_its_style_before_paint(client, test_db, mock_ha_client, style):
    await _token(slug=f"page-{style}", page_style=style)
    html = (await client.get(f"/g/page-{style}")).text
    head = html.split("</head>")[0]
    # The skin script and stylesheet load in <head>, and the call that applies
    # the link's style runs there too, ahead of any card.
    assert "/static/skin.js?v=" in head and "/static/skins.css?v=" in head
    assert f'applyPageSkin("{style}");' in head


@pytest.mark.skipif(node is None, reason="node is not installed")
async def test_dashboard_picker_loads_and_saves_the_style(client, admin_session, mock_ha_client):
    out = await _dashboard(client, admin_session, DASH_SEED + """
    replies.push({ ok: true, body: { ...TOKEN, page_style: 'device' } });
    await openEditModal('t1');
    const html = els('edit-picker').innerHTML;
    fire('change', { dataset: { action: 'picker-page-style', container: 'edit-picker' }, value: 'ios', closest: () => null });
    replies.push({ ok: true, body: TOKEN });
    await submitEditEntities();
    const patch = calls.filter(c => c.url.endsWith('/admin/tokens/t1/entities')).pop().body;
    openCreateModal();
    console.log(JSON.stringify({ html, sent: patch.page_style, fresh: createPicker.pageStyle }));
    """)
    assert '<option value="device" selected>' in out["html"]
    assert "Match the guest&#39;s phone" in out["html"] or "Match the guest's phone" in out["html"]
    assert out["sent"] == "ios"
    assert out["fresh"] == "standard"

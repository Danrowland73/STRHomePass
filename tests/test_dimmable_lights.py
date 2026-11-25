"""Dimmable lights get a brightness slider automatically.

Home Assistant says what a light can do in supported_color_modes (or, for older
integrations, bit 1 of supported_features). Any mode but "onoff" dims, so the
guest page draws a slider for it, on or off, unless the link sets
hide_brightness for that light. Colour stays opt-in.

Same node harness as tests/test_group_headings_js.py. Skipped without node.
"""

import pytest

from tests.test_group_headings_js import DASH_SEED, _dashboard, _guest
from tests.test_picker_js import node

pytestmark = pytest.mark.skipif(node is None, reason="node is not installed")

LIGHTS = """
const light = (state, attrs) => ({ entity_id: 'light.x', state, attributes: { friendly_name: 'Lamp', ...attrs } });
const DIM = { supported_color_modes: ['brightness'] };
const slider = html => {
  const m = html.match(/<input type="range" min="0" max="100" value="(\\d+)" id="bri-light-x"/);
  return m ? Number(m[1]) : null;
};
"""


async def test_what_counts_as_dimmable(client, sample_token, mock_ha_client):
    out = await _guest(client, LIGHTS + """
    const cases = {
      brightness: { supported_color_modes: ['brightness'] },
      color_temp: { supported_color_modes: ['color_temp'] },
      rgb: { supported_color_modes: ['hs', 'onoff'] },
      onoff: { supported_color_modes: ['onoff'] },
      legacy_dimmer: { supported_features: 1 },
      legacy_switch: { supported_features: 0 },
      unavailable: {},
    };
    const out = {};
    for (const [k, attrs] of Object.entries(cases)) out[k] = lightSupportsBrightness(light('off', attrs));
    console.log(JSON.stringify(out));
    """)
    assert out == {
        "brightness": True, "color_temp": True, "rgb": True, "onoff": False,
        "legacy_dimmer": True, "legacy_switch": False, "unavailable": False,
    }


async def test_a_dimmable_light_gets_a_slider_on_or_off(client, sample_token, mock_ha_client):
    out = await _guest(client, LIGHTS + """
    entityMeta = {};
    console.log(JSON.stringify({
      on: slider(buildCard('light.x', light('on', { ...DIM, brightness: 128 }))),
      off: slider(buildCard('light.x', light('off', DIM))),
      onoff: slider(buildCard('light.x', light('on', { supported_color_modes: ['onoff'] }))),
      unavailable: slider(buildCard('light.x', light('unavailable', {}))),
    }));
    """)
    # 128/255 is 50%; an off light sits at 0, which is also what turns it off.
    assert out == {"on": 50, "off": 0, "onoff": None, "unavailable": None}


async def test_the_admin_can_keep_a_dimmable_light_on_off(client, sample_token, mock_ha_client):
    out = await _guest(client, LIGHTS + """
    entityMeta = { 'light.x': { options: { hide_brightness: true } } };
    const hidden = slider(buildCard('light.x', light('on', { ...DIM, brightness: 255 })));
    // The old opt-in key is harmless: it neither hides nor is needed.
    entityMeta = { 'light.x': { options: { show_brightness: true } } };
    const legacy = slider(buildCard('light.x', light('on', { ...DIM, brightness: 255 })));
    console.log(JSON.stringify({ hidden, legacy }));
    """)
    assert out == {"hidden": None, "legacy": 100}


async def test_a_dimmable_light_is_a_wide_card_in_the_phone_looks(client, sample_token, mock_ha_client):
    out = await _guest(client, LIGHTS + """
    entityMeta = {};
    console.log(JSON.stringify({
      dim: buildCard('light.x', light('off', DIM)),
      plain: buildCard('light.x', light('off', { supported_color_modes: ['onoff'] })),
    }));
    """)
    assert "data-tile" not in out["dim"]
    assert "data-tile" in out["plain"]


async def test_dashboard_option_is_ticked_unless_hidden(client, admin_session, mock_ha_client):
    out = await _dashboard(client, admin_session, DASH_SEED + """
    openCreateModal();
    createPicker.selected.add('light.a');
    openEntityModal('create-picker', 'light.a');
    const fresh = els('entity-show-brightness').checked;
    els('entity-show-brightness').checked = false;
    submitEntityMeta();
    const saved = JSON.parse(JSON.stringify(createPicker.meta['light.a'].options));
    openEntityModal('create-picker', 'light.a');
    const reopened = els('entity-show-brightness').checked;
    els('entity-show-brightness').checked = true;
    submitEntityMeta();
    const cleared = (createPicker.meta['light.a'] || {}).options || {};
    console.log(JSON.stringify({ fresh, saved, reopened, cleared }));
    """)
    assert out["fresh"] is True
    assert out["saved"] == {"hide_brightness": True}
    assert out["reopened"] is False
    assert "hide_brightness" not in out["cleared"]


async def test_hide_brightness_is_stored(client, admin_session, mock_ha_client):
    resp = await client.post("/admin/tokens", cookies=admin_session, json={
        "label": "Cottage", "entity_ids": ["light.living_room"], "expires_in_seconds": 3600,
        "entity_meta": {"light.living_room": {"options": {"hide_brightness": True}}},
    })
    assert resp.status_code in (200, 201), resp.text
    token = (await client.get(f"/admin/tokens/{resp.json()['id']}", cookies=admin_session)).json()
    assert token["entity_meta"]["light.living_room"]["options"] == {"hide_brightness": True}

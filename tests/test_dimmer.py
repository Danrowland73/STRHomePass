"""The iOS look's dimmer tiles, after the phone's own home app.

In the iOS look a dimmable light is a plain tile: its bulb toggles it, and the
rest of the tile opens a tall vertical slider. Every other look keeps the
inline slider. Same node harness as tests/test_group_headings_js.py.
"""
import pytest

from tests.test_group_headings_js import _guest
from tests.test_picker_js import node

pytestmark = pytest.mark.skipif(node is None, reason="node is not installed")

SEED = """
const light = (state, attrs) => ({ entity_id: 'light.x', state, attributes: { friendly_name: 'Lamp', ...attrs } });
const DIM = { supported_color_modes: ['brightness'] };
entityMeta = {};
const sent = [];
sendCmd = async (eid, domain, service, data = {}) => { sent.push([eid, `${domain}.${service}`, data]); };
// A stand-in for a tapped element: the delegated handler reads its dataset.
function tap(dataset) {
  const el = { dataset, tagName: 'DIV', classList: { toggle() {}, contains() { return false; } }, setAttribute() {} };
  el.closest = sel => (sel === '[data-action]' ? el : null);
  fire('click', el);
}
const ios = () => { document.documentElement.dataset.skin = 'ios'; };
"""


async def test_ios_look_draws_a_dimmable_light_as_a_tile(client, sample_token, mock_ha_client):
    out = await _guest(client, SEED + """
    ios();
    const dimmable = buildCard('light.x', light('on', { ...DIM, brightness: 128 }));
    const plain = buildCard('light.x', light('on', { supported_color_modes: ['onoff'] }));
    document.documentElement.dataset.skin = undefined;
    const standard = buildCard('light.x', light('on', { ...DIM, brightness: 128 }));
    console.log(JSON.stringify({ dimmable, plain, standard }));
    """)
    d = out["dimmable"]
    assert "data-tile" in d
    assert 'data-action="open-dimmer"' in d and 'aria-haspopup="dialog"' in d
    assert 'data-action="shape-toggle"' in d and 'aria-label="Toggle Lamp"' in d
    assert 'type="range"' not in d
    assert "On · 50%" in d
    # An on/off light is unchanged: the whole tile toggles.
    assert 'data-action="card-toggle"' in out["plain"] and "shape-toggle" not in out["plain"]
    # Other looks keep the inline slider.
    assert 'data-action="open-dimmer"' not in out["standard"]
    assert 'data-range-action="brightness"' in out["standard"]


async def test_bulb_toggles_and_tile_opens_the_dimmer(client, sample_token, mock_ha_client):
    out = await _guest(client, SEED + """
    ios();
    states = { 'light.x': light('on', { ...DIM, brightness: 191 }) };
    tap({ action: 'shape-toggle', eid: 'light.x', domain: 'light' });
    const afterBulb = sent.length;
    // The bulb's toggle flips the state optimistically; reset it to read the dimmer.
    states = { 'light.x': light('on', { ...DIM, brightness: 191 }) };
    tap({ action: 'open-dimmer', eid: 'light.x' });
    const el = id => document.getElementById(id);
    console.log(JSON.stringify({
      sent, afterBulb, open: dimmer.eid,
      title: el('dimmer-title').textContent, value: el('dimmer-value').textContent,
      fill: el('dimmer-fill').style.height,
    }));
    """)
    assert out["afterBulb"] == 1
    # The bulb turns an on light off.
    assert out["sent"][0][:2] == ["light.x", "light.turn_off"]
    assert out["open"] == "light.x"
    assert out["title"] == "Lamp"
    assert (out["value"], out["fill"]) == ("75%", "75%")


async def test_dragging_sends_brightness_throttled_and_the_last_value_always(client, sample_token, mock_ha_client):
    out = await _guest(client, SEED + """
    ios();
    states = { 'light.x': light('off', DIM) };
    openDimmer('light.x');
    setDimmer(30);          // first move goes straight out
    setDimmer(45);          // inside the throttle window: held
    setDimmer(60);          // replaces it
    const midDrag = sent.slice();
    closeDimmer();          // closing flushes the held value
    const afterClose = sent.slice();
    openDimmer('light.x');
    setDimmer(-20);         // clamped, and 0 is off; held by the throttle...
    const reopened = dimmer.eid;
    closeDimmer();          // ...and flushed on close
    console.log(JSON.stringify({ midDrag, afterClose, last: sent[sent.length - 1], open: reopened }));
    """)
    brightness = lambda calls: [c[2].get("brightness") for c in calls]
    # 30% and 60% of 255, rounded half-up as the page does.
    assert brightness(out["midDrag"]) == [77]
    assert brightness(out["afterClose"]) == [77, 153]
    assert out["last"][1] == "light.turn_on" and out["last"][2] == {"brightness": 0}
    assert out["open"] == "light.x"


async def test_echoes_do_not_yank_the_slider_mid_drag(client, sample_token, mock_ha_client):
    out = await _guest(client, SEED + """
    ios();
    states = { 'light.x': light('on', { ...DIM, brightness: 255 }) };
    openDimmer('light.x');
    // Untouched, HA's updates move the slider.
    syncDimmer(light('on', { ...DIM, brightness: 51 }));
    const synced = dimmer.pct;
    // Just after the guest moved it, an older echo is ignored.
    setDimmer(80);
    syncDimmer(light('on', { ...DIM, brightness: 51 }));
    console.log(JSON.stringify({ synced, held: dimmer.pct }));
    """)
    assert out == {"synced": 20, "held": 80}


async def test_backdrop_and_done_close_but_the_dialog_does_not(client, sample_token, mock_ha_client):
    out = await _guest(client, SEED + """
    ios();
    states = { 'light.x': light('on', { ...DIM, brightness: 255 }) };
    openDimmer('light.x');
    tap({ action: 'dimmer-dialog' });
    const afterDialog = dimmer.eid;
    tap({ action: 'dimmer-close' });
    console.log(JSON.stringify({ afterDialog, afterClose: dimmer.eid }));
    """)
    assert out == {"afterDialog": "light.x", "afterClose": None}


async def test_guest_page_carries_the_dimmer(client, sample_token, mock_ha_client):
    html = (await client.get("/g/test-token")).text
    assert 'id="dimmer-backdrop"' in html
    assert 'id="dimmer-track" class="dimmer-track" role="slider" tabindex="0"' in html

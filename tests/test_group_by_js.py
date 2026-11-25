"""The type/area layout in the browser: the guest page's sections and switch,
and the dashboard picker's layout controls.

Same harness as tests/test_group_headings_js.py: the real page is rendered
through its route and its inline script is run in node against the stub DOM.
Skipped when node is not installed.
"""
import re

import pytest

from tests.test_group_headings_js import (
    DASH_SEED, GUEST_SEED, _dashboard, _guest, _headings, _toggles,
)
from tests.test_picker_js import node

pytestmark = pytest.mark.skipif(node is None, reason="node is not installed")

# A storage stand-in that remembers, so a pick can be read back.
STORE = """
const store = {};
globalThis.localStorage = window.localStorage = {
  getItem(k) { storageLog.push(['get', k]); return k in store ? store[k] : null; },
  setItem(k, v) { storageLog.push(['set', k]); store[k] = String(v); },
  removeItem(k) { delete store[k]; },
};
"""

AREA_SEED = GUEST_SEED + STORE + """
// The Display by switch renders into its toolbar slot above the cards; page()
// is both, as a guest sees them.
const slot = () => document.getElementById('layout-switch-slot').innerHTML;
const page = () => slot() + html();
groupHeadings = { light: { name: 'Lamps', locked: true } };
const layout = (over = {}) => readLayout({
  group_by: 'area', guest_can_regroup: true,
  entity_areas: { 'light.a': 'kitchen', 'switch.b': 'kitchen', 'lock.d': 'attic' },
  area_names: { kitchen: 'Kitchen', attic: 'Attic' },
  ...over,
});
// A stand-in for a switch button: the delegated handler reads its dataset.
function pick(value) {
  const btn = { dataset: { action: 'group-by', groupBy: value }, tagName: 'BUTTON' };
  btn.closest = sel => (sel === '[data-action]' ? btn : null);
  fire('click', btn);
}
"""


def _switch(html: str) -> dict[str, str]:
    """The layout switch's buttons: value -> aria-pressed."""
    return dict(re.findall(r'data-action="group-by" data-group-by="(\w+)" aria-pressed="(\w+)"', html))


async def test_area_layout_draws_one_section_per_area(client, sample_token, mock_ha_client):
    out = await _guest(client, AREA_SEED + """
    layout();
    renderAll();
    console.log(JSON.stringify(page()));
    """)
    # Alphabetical, with the entity that has no area last. Renamed and locked
    # type headings do not apply to areas.
    assert _headings(out) == ["Attic", "Kitchen", "No area"]
    assert _toggles(out) == ["area-attic", "area-kitchen", "area-none"]
    # Inside an area the cards keep the type order: the light before the switch.
    kitchen = out.split('id="group-area-kitchen"')[1]
    assert kitchen.index("card-light-a") < kitchen.index("card-switch-b")
    assert _switch(out) == {"type": "false", "area": "true"}
    # The switch sits in the toolbar beside the theme switch, not among the cards.
    assert out.index('id="layout-switch-label"') < out.index('data-group=')
    # A visible label, which also names the switch for screen readers.
    assert '<span id="layout-switch-label" class="text-xs font-semibold text-muted">Display by:</span>' in out
    assert 'role="group" aria-labelledby="layout-switch-label"' in out


async def test_the_switch_is_drawn_in_the_toolbar_not_the_cards(client, sample_token, mock_ha_client):
    out = await _guest(client, AREA_SEED + """
    layout();
    renderAll();
    const withAreas = { slot: slot(), cards: html() };
    // With nothing on the link the slot is emptied too.
    entityOrder = [];
    renderAll();
    console.log(JSON.stringify({ ...withAreas, emptied: slot() }));
    """)
    assert 'data-action="group-by"' in out["slot"]
    assert 'data-action="group-by"' not in out["cards"]
    assert out["emptied"] == ""


async def test_type_layout_is_unchanged(client, sample_token, mock_ha_client):
    out = await _guest(client, AREA_SEED + """
    layout({ group_by: 'type' });
    renderAll();
    console.log(JSON.stringify(page()));
    """)
    assert _headings(out) == ["Lamps", "Switches", "Locks"]
    assert _switch(out) == {"type": "true", "area": "false"}


async def test_guest_pick_is_remembered_per_link(client, sample_token, mock_ha_client):
    out = await _guest(client, AREA_SEED + """
    layout();
    renderAll();
    pick('type');
    const after = page();
    // A refetch keeps the guest's pick over the link's default.
    layout();
    renderAll();
    console.log(JSON.stringify({ after, again: page(), store }));
    """)
    assert _headings(out["after"]) == ["Lamps", "Switches", "Locks"]
    assert _headings(out["again"]) == ["Lamps", "Switches", "Locks"]
    assert out["store"] == {"hp-group-by:test-token": "type"}


async def test_no_switch_when_the_guest_may_not_regroup(client, sample_token, mock_ha_client):
    out = await _guest(client, AREA_SEED + """
    store['hp-group-by:test-token'] = 'type';
    storageLog.length = 0;
    layout({ guest_can_regroup: false });
    renderAll();
    console.log(JSON.stringify({ html: page(), storageLog }));
    """)
    # The admin's layout wins over a pick made while switching was allowed,
    # and storage is not even read.
    assert _headings(out["html"]) == ["Attic", "Kitchen", "No area"]
    assert _switch(out["html"]) == {}
    assert out["storageLog"] == []


async def test_no_areas_means_type_layout_and_no_switch(client, sample_token, mock_ha_client):
    out = await _guest(client, AREA_SEED + """
    storageLog.length = 0;
    layout({ area_names: null, entity_areas: {} });
    renderAll();
    const unreadable = page();
    layout({ area_names: {}, entity_areas: {} });
    renderAll();
    console.log(JSON.stringify({ unreadable, empty: page(), storageLog }));
    """)
    for html in (out["unreadable"], out["empty"]):
        assert _headings(html) == ["Lamps", "Switches", "Locks"]
        assert _switch(html) == {}
    assert out["storageLog"] == []


async def test_dashboard_picker_loads_and_saves_the_layout(client, admin_session, mock_ha_client):
    out = await _dashboard(client, admin_session, DASH_SEED + """
    const change = (action, container, extra) =>
      fire('change', { dataset: { action, container }, closest: () => null, ...extra });
    replies.push({ ok: true, body: { ...TOKEN, group_by: 'area', guest_can_regroup: false } });
    await openEditModal('t1');
    const html = els('edit-picker').innerHTML;
    change('picker-group-by', 'edit-picker', { value: 'type' });
    change('picker-guest-regroup', 'edit-picker', { checked: true });
    replies.push({ ok: true, body: TOKEN });
    await submitEditEntities();
    const patch = calls.filter(c => c.url.endsWith('/admin/tokens/t1/entities')).pop().body;

    openCreateModal();
    els('f-label').value = 'Guest';
    createPicker.selected.add('light.a');
    replies.push({ ok: true, body: { slug: 'abc' } });
    await submitCreate();
    const create = calls.filter(c => c.url.endsWith('/admin/tokens') && c.method === 'POST').pop().body;
    console.log(JSON.stringify({ html, patch, create }));
    """)
    assert re.search(r'value="area" checked\s+data-action="picker-group-by"', out["html"])
    assert re.search(r'<input type="checkbox" \s+data-action="picker-guest-regroup"', out["html"])
    assert "Guest page layout" in out["html"]
    assert (out["patch"]["group_by"], out["patch"]["guest_can_regroup"]) == ("type", True)
    # A new link starts as the page always was.
    assert (out["create"]["group_by"], out["create"]["guest_can_regroup"]) == ("type", True)


async def test_duplicate_carries_the_layout(client, admin_session, mock_ha_client):
    out = await _dashboard(client, admin_session, DASH_SEED + """
    replies.push({ ok: true, body: { ...TOKEN, group_by: 'area', guest_can_regroup: false } });
    await duplicateToken('t1');
    console.log(JSON.stringify([createPicker.groupBy, createPicker.guestCanRegroup]));
    """)
    assert out == ["area", False]

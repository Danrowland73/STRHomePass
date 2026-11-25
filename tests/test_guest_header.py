"""The guest page header: the link name and app name fit the device's width,
and the theme switch sits in the toolbar above the devices, next to Display by.
"""
import re


async def test_theme_switch_moved_from_the_header_to_the_toolbar(client, sample_token, mock_ha_client):
    html = (await client.get("/g/test-token")).text
    header = html[html.index("<header"):html.index("</header>")]
    toolbar = html[html.index('id="page-toolbar"'):html.index('id="cards-container"')]
    assert "theme-toggle" not in header
    assert 'id="conn-badge"' in header
    assert "theme-toggle" in toolbar
    assert toolbar.count('data-action="set-theme"') == 3
    # The Display by switch's slot shares the row.
    assert 'id="layout-switch-slot"' in toolbar


async def test_link_name_and_app_name_fit_the_width(client, sample_token, mock_ha_client):
    html = (await client.get("/g/test-token")).text
    header = html[html.index("<header"):html.index("</header>")]
    fits = re.findall(r'<div data-fit data-fit-max="(\d+)" data-fit-min="(\d+)"[^>]*>([^<]*)</div>', header)
    assert fits == [("40", "18", "Test Token"), ("18", "11", "Home Access")]
    # Sized before the first paint: the script follows the header directly.
    after = html[html.index("</header>"):]
    assert after[len("</header>"):].lstrip().startswith("<script nonce=")
    assert "function fitHeaderText()" in after.split("</script>")[0]

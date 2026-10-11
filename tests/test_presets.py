"""CI validation of the designer's preset library (plan §5.4)."""

from ui_agent import settings
from ui_agent.color import check_palette, palette_matches_direction


def test_example_palettes_pass_aa_and_ranges_in_both_themes():
    for d in settings.presets()["colors"]["directions"]:
        assert d["examples"], d["id"]
        for ex in d["examples"]:
            for theme in ("light", "dark"):
                pal = ex[theme]
                assert set(pal) == set(settings.presets()["colors"]["roles"]), (d["id"], theme)
                assert not check_palette(pal), (d["id"], theme, check_palette(pal))
                assert not palette_matches_direction(pal, d), (d["id"], theme, palette_matches_direction(pal, d))


def test_fonts_come_from_allowlist():
    allowed = settings.presets()["typography"]["font_allowlist_hosts"]
    assert allowed == ["fonts.googleapis.com", "fonts.gstatic.com"]
    for t in settings.presets()["typography"]["pairings"]:
        assert t["google"].startswith("family="), t["id"]
        for role in ("heading", "body"):
            assert t[role]["family"].replace(" ", "+") in t["google"], (t["id"], role)


def test_every_layout_and_default_section_is_defined():
    lp = settings.presets()["layouts"]
    sections = {s["id"] for s in lp["sections"]}
    for pt in lp["page_types"]:
        assert any(l["page_type"] == pt["id"] for l in lp["layouts"]), f"no layouts for {pt['id']}"
        assert set(pt["default_sections"]) <= sections, pt["id"]


def test_every_preset_is_described_for_the_planner():
    p = settings.presets()
    assert all(s.get("guidance") for s in p["styles"]["styles"])
    assert all(l.get("brief") for l in p["layouts"]["layouts"])
    assert all(d.get("hint") and len(d["examples"]) >= 2 for d in p["colors"]["directions"])
    assert all(t.get("heading") and t.get("body") for t in p["typography"]["pairings"])
    for group in ("density", "shapes", "motion", "imagery"):
        assert all(o.get("hint") for o in p["options"][group]), group

"""CI validation of presets (plan §5.4)."""

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


def test_every_layout_renders_a_wireframe_for_its_page_type_sections():
    lp = settings.presets()["layouts"]
    sections = {s["id"]: s for s in lp["sections"]}
    for pt in lp["page_types"]:
        layouts = [l for l in lp["layouts"] if l["page_type"] == pt["id"]]
        assert layouts, f"no layouts for {pt['id']}"
        for l in layouts:
            for sid in pt["default_sections"]:
                assert sid in sections, sid
                rows = l["overrides"].get(sid) or sections[sid]["rows"] or (l["hero"] if sid == "hero" else None)
                assert rows is not None, (l["id"], sid)
                for r in rows:
                    assert sum(c["span"] + c.get("offset", 0) for c in r["cols"]) <= 12, (l["id"], sid)


def test_every_preset_has_samples():
    p = settings.presets()
    assert all(s.get("sample") for s in p["styles"]["styles"])
    assert all(d.get("swatches") and len(d["examples"]) >= 2 for d in p["colors"]["directions"])
    assert all(t.get("heading") and t.get("body") for t in p["typography"]["pairings"])
    for group in ("density", "shapes", "motion", "imagery", "themes", "tones"):
        assert all(o.get("hint") for o in p["options"][group]), group

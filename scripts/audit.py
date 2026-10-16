"""Internal dev tool (M0): run the Layer-A checks on one HTML file.

    python scripts/audit.py page.html [--json]
"""

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ui_agent.tools.browser import get_browser  # noqa: E402
from ui_agent.tools.checks import detect_slop, run_layer_a  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="directory for screenshots (default: temp dir)")
    a = ap.parse_args()
    path = Path(a.html)
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="audit-"))
    try:
        render = await get_browser().render(path, out)
    finally:
        await get_browser().close()
    audit = run_layer_a(render, path.read_text(), await detect_slop(path))
    if a.json:
        print(json.dumps(audit.model_dump(), indent=2))
    else:
        for c in audit.checks:
            print(f"{'PASS' if c.passed else 'FAIL' if c.blocking else 'WARN'}  {c.id} {c.name}: {c.details}")
            for item in c.items[:5] if not c.passed else []:
                print(f"        - {json.dumps(item)[:160]}")
        print(f"\n{'All checks pass' if audit.passed else 'Audit failed'}. Screenshots: {out}")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

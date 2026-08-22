"""Generate assets/dictate.icns for the macOS .app bundle.

Pillow can write a multi-resolution .icns directly from one large master image,
so this works on any OS (no macOS-only `iconutil` required).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from icon_loader import render_logo  # noqa: E402

OUT = ROOT / "assets" / "dictate.icns"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    master = render_logo(1024)
    master.save(OUT, format="ICNS")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

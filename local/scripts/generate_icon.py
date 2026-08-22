"""Generate assets/dictate.ico for the Windows .exe and shortcuts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from icon_loader import render_logo  # noqa: E402

OUT = ROOT / "assets" / "dictate.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [render_logo(size) for size in SIZES]
    images[0].save(
        OUT,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
        append_images=images[1:],
    )
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

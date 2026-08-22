"""Download punctuation ONNX model for bundled Dictate builds."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from punctuation_assets import download_punctuation_model  # noqa: E402


if __name__ == "__main__":
    download_punctuation_model(ROOT / "assets" / "punctuation")

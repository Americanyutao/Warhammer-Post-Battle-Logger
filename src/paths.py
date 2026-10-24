"""Read-only packaged resources and separate writable capture location."""
from pathlib import Path
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
DATA_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
RESOURCE_ROOT = Path(sys._MEIPASS) if FROZEN else DATA_ROOT


def resource_path(relative):
    return RESOURCE_ROOT / relative

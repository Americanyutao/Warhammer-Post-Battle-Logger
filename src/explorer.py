"""Open shareables normally, after the finished export and menu update."""
import os
from pathlib import Path
import time


def open_folder(path):
    path=Path(path).resolve()
    # The export is already complete. Yield a moment for its status to paint;
    # do not create, minimize, move or prepare an Explorer window ahead of time.
    time.sleep(.35)
    os.startfile(str(path))

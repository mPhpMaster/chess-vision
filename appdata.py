"""Where Chess Vision keeps its saved files (calibration, puzzle records).

Files live in %APPDATA%\\ChessVision so they survive updates and work when the
app is installed under Program Files. Files from older versions, which were
saved next to the scripts, are copied over on first use.
"""
import os
import shutil
import sys

APP_NAME = "Chess Vision"
APP_VERSION = "1.0.0"

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ChessVision")


def data_path(name):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    legacy = os.path.join(SOURCE_DIR, name)
    if not getattr(sys, "frozen", False) and not os.path.exists(path) and os.path.exists(legacy):
        shutil.copy2(legacy, path)
    return path

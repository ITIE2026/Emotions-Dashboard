from __future__ import annotations

import os
import sys


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(PACKAGE_DIR, "vendor")
ASSETS_DIR = os.path.join(PACKAGE_DIR, "assets")

if VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)


STATE_IMAGE_FILES = {
    "OPEN": "hand-open.png",
    "NEUTRAL": "hand-neutral.png",
    "CLOSED": "hand-close.png",
}


def asset_path(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


def hand_image_path(state: str) -> str:
    filename = STATE_IMAGE_FILES.get(state.upper(), STATE_IMAGE_FILES["OPEN"])
    return asset_path(filename)

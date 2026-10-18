#!/usr/bin/env python3
"""Apply the bundled Riot icon to Riot X11 windows during launcher startup."""
import ctypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image


def xprop(*args: str) -> str:
    result = subprocess.run(["xprop", *args], capture_output=True, text=True, check=False)
    return result.stdout if result.returncode == 0 else ""


def set_icon(display: int, window_id: int, values: list[int]) -> None:
    x11 = ctypes.CDLL("libX11.so.6")
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XChangeProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
    ]
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    prop = x11.XInternAtom(display, b"_NET_WM_ICON", 0)
    cardinal = x11.XInternAtom(display, b"CARDINAL", 0)
    data = (ctypes.c_ulong * len(values))(*values)
    x11.XChangeProperty(display, window_id, prop, cardinal, 32, 0, data, len(values))
    x11.XSync(display, 0)


def main() -> int:
    if not os.environ.get("DISPLAY"):
        return 0
    icon_path = Path(sys.argv[1])
    image = Image.open(icon_path).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
    raw = image.tobytes()
    pixels = [
        (raw[i + 3] << 24) | (raw[i] << 16) | (raw[i + 1] << 8) | raw[i + 2]
        for i in range(0, len(raw), 4)
    ]
    values = [32, 32, *pixels]

    x11 = ctypes.CDLL("libX11.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        return 0

    updated: set[str] = set()
    deadline = time.monotonic() + float(os.environ.get("DARLING_RIOT_ICON_WAIT_SECONDS", "300"))
    try:
        while time.monotonic() < deadline:
            clients = xprop("-root", "_NET_CLIENT_LIST")
            for match in re.finditer(r"0x[0-9a-fA-F]+", clients):
                window = match.group()
                if window in updated:
                    continue
                wm_class = xprop("-id", window, "WM_CLASS")
                if not re.search(r"riot", wm_class, re.IGNORECASE):
                    continue
                set_icon(display, int(window, 16), values)
                updated.add(window)
            time.sleep(1)
    finally:
        x11.XCloseDisplay(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

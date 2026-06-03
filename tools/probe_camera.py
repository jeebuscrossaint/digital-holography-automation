"""Probe the camera with every URL form we can think of.

Goal: find which URL produces a non-zero frame. Tries:

  1. cam://0
  2. cam://0?fg=none
  3. cam://0?fg=XFrameGrabberNative
  4. gev://<ip>          (IP discovered from enumerate_devices)
  5. The exact device.url that enumeration reports

For each: open, load calibration, start capture, grab 3 frames,
report min/max/mean of each. The one with non-zero stats is the
URL we should be using.

Run with Xeneth closed:
    uv run python tools/probe_camera.py
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("hardware", "lib"):
    p = ROOT / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

_XENETH = r"C:\Program Files\Common Files\XenICs\Runtime"
if os.path.exists(_XENETH):
    try: os.add_dll_directory(_XENETH)
    except (AttributeError, OSError): pass
    os.environ["PATH"] = _XENETH + os.pathsep + os.environ.get("PATH", "")

import numpy as np
from xenics.xeneth import (XCamera, XEnumerationFlags,
                            XGetFrameFlags, enumerate_devices)
from xenics.xeneth.errors import XenethAPIException


CAL = r"C:\Program Files\Xeneth\Calibrations\XC-(10-06-2021)-500us_14931.xca"
if not os.path.exists(CAL):
    CAL = str(ROOT / "hardware" / "calibration" / "XC-(10-06-2021)-500us_14931.xca")


def try_url(url: str) -> None:
    print(f"\n{'='*70}\n  URL: {url}\n{'='*70}")
    cam = XCamera()
    try:
        cam.open(url)
        if not cam.is_initialized:
            print("  open() did NOT initialize")
            return
        try:
            pid = cam.get_property_value("_CAM_PID")
            ser = cam.get_property_value("_CAM_SER")
            print(f"  PID=0x{int(pid):X}  SER={ser}")
        except Exception as e:
            print(f"  property read failed: {e}")

        try:
            cam.load_calibration(CAL, 2)
            print(f"  calibration loaded ({CAL})")
        except Exception as e:
            print(f"  calibration load failed: {e}")

        buf = cam.create_buffer()
        cam.start_capture()
        print(f"  is_capturing = {cam.is_capturing}")
        time.sleep(0.3)

        for i in range(3):
            t0 = time.monotonic()
            try:
                ok = cam.get_frame(buf, flags=XGetFrameFlags.XGF_Blocking)
            except XenethAPIException as e:
                print(f"  frame {i}: EXCEPTION {e}")
                continue
            dt = (time.monotonic() - t0) * 1000
            if not ok:
                print(f"  frame {i}: get_frame returned False  ({dt:.0f} ms)")
                continue
            arr = np.asarray(buf.image_data)
            print(f"  frame {i}: shape={arr.shape}  dtype={arr.dtype}  "
                  f"min={int(arr.min())}  max={int(arr.max())}  "
                  f"mean={float(arr.mean()):.1f}  ({dt:.0f} ms)")
    except XenethAPIException as e:
        print(f"  OPEN FAILED: {e}")
    finally:
        try:
            if cam.is_capturing: cam.stop_capture()
        except Exception: pass
        try: cam.close()
        except Exception: pass


def main():
    print("Enumerating devices…")
    devs = enumerate_devices(XEnumerationFlags.XEF_EnableAll)
    enum_urls = []
    for i, d in enumerate(devs):
        print(f"  [{i}] {d.name}  serial={d.serial}  url={d.url}  state={d.state}")
        enum_urls.append(d.url)
    print()

    candidates = [
        "cam://0",
        "cam://0?fg=none",
        "cam://0?fg=XFrameGrabberNative",
    ] + enum_urls

    # de-dup while preserving order
    seen = set(); ordered = []
    for u in candidates:
        if u and u not in seen:
            ordered.append(u); seen.add(u)

    for u in ordered:
        try_url(u)


if __name__ == "__main__":
    main()

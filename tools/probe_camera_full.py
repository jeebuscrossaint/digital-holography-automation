"""Full property dump + try gev:// URL + try TLParamsLocked.

probe_camera tested cam://0 variants; all timed out except fg=none
(which doesn't really grab). probe_camera_props found the camera is
in FreeRunning / Continuous mode with no obvious blocker, and
AcquisitionStart didn't unblock it.

Next hypotheses to test:
  1. The right URL form is gev://<IP>, not cam://0. The Xeneth
     connection setup showed the camera at 169.254.133.25.
  2. GigE Vision standard requires TLParamsLocked=1 before AcquisitionStart
     to bind streaming channel params. Try if that property exists.
  3. Maybe something else entirely — dump ALL 237 properties to file
     so we can grep for what looks unusual.

Outputs:
  - Stream test results for several URLs
  - Full property dump → tools/probe_camera_full_props.txt

Run with Xeneth closed:
    uv run python tools/probe_camera_full.py
"""

import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("hardware", "lib"):
    p = ROOT / sub
    if str(p) not in sys.path and p.exists():
        sys.path.insert(0, str(p))

_XENETH = r"C:\Program Files\Common Files\XenICs\Runtime"
if os.path.exists(_XENETH):
    try: os.add_dll_directory(_XENETH)
    except (AttributeError, OSError): pass
    os.environ["PATH"] = _XENETH + os.pathsep + os.environ.get("PATH", "")

import numpy as np
from xenics.xeneth import XCamera, XEnumerationFlags, XGetFrameFlags, enumerate_devices
from xenics.xeneth.capi.enums import XPropType
from xenics.xeneth.errors import XenethAPIException


CAL = r"C:\Program Files\Xeneth\Calibrations\XC-(10-06-2021)-500us_14931.xca"
if not os.path.exists(CAL):
    CAL = str(ROOT / "hardware" / "calibration" / "XC-(10-06-2021)-500us_14931.xca")


def dump_all_properties_to_file(out_path: str):
    cam = XCamera()
    cam.open("cam://0?fg=none")
    if not cam.is_initialized:
        return
    n = cam.get_property_count()
    base_names = {
        XPropType.XType_Base_Number: "Number",
        XPropType.XType_Base_Enum:   "Enum",
        XPropType.XType_Base_Bool:   "Bool",
        XPropType.XType_Base_String: "String",
        XPropType.XType_Base_Blob:   "Blob",
        XPropType.XType_Base_Action: "Action",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Total properties: {n}\n\n")
        for i in range(n):
            try:
                name = cam.get_property_name(i)
                ptype = cam.get_property_type(name)
                base = ptype & XPropType.XType_Base_Mask
                tname = base_names.get(base, str(ptype))
                prange = cam.get_property_range(name)
                try: val = cam.get_property_value(name)
                except Exception: val = "<unreadable>"
                f.write(f"[{i:3}] {name}\n")
                f.write(f"      type={tname}  range={prange}\n")
                f.write(f"      value={val}\n\n")
            except Exception as e:
                f.write(f"[{i:3}] <error: {e}>\n\n")
    cam.close()
    print(f"\nFull property dump → {out_path}")


def try_url(url: str, with_tl_lock: bool = False):
    print(f"\n{'='*70}\n  URL: {url}{'  +TLParamsLocked' if with_tl_lock else ''}\n{'='*70}")
    cam = XCamera()
    try:
        cam.open(url)
        if not cam.is_initialized:
            print("  not initialized")
            return

        try:
            cam.load_calibration(CAL, 2)
            print(f"  cal loaded")
        except Exception as e:
            print(f"  cal failed: {e}")

        # Some GigE Vision libs require this before streaming
        if with_tl_lock:
            for n in ("TLParamsLocked", "GevTLParamsLocked"):
                try:
                    cam.set_property_value(n, 1)
                    print(f"  set {n}=1")
                except Exception as e:
                    print(f"  {n} not available ({e})")

        buf = cam.create_buffer()
        cam.start_capture()
        print(f"  is_capturing = {cam.is_capturing}")

        try:
            cam.set_property_value("AcquisitionStart", 1)
            print("  AcquisitionStart fired")
        except Exception as e:
            print(f"  AcquisitionStart: {e}")

        time.sleep(0.5)

        for i in range(3):
            t0 = time.monotonic()
            try:
                ok = cam.get_frame(buf, flags=XGetFrameFlags.XGF_Blocking)
            except XenethAPIException as e:
                print(f"  frame {i}: EXC {e}")
                continue
            dt = (time.monotonic() - t0) * 1000
            if not ok:
                print(f"  frame {i}: False  ({dt:.0f} ms)")
                continue
            arr = np.asarray(buf.image_data)
            print(f"  frame {i}: min={int(arr.min())}  max={int(arr.max())}  "
                  f"mean={float(arr.mean()):.1f}  ({dt:.0f} ms)")

        # check lost-frames counter
        try:
            lost = cam.get_property_value("XGIGEV_LostFrames")
            print(f"  XGIGEV_LostFrames = {lost}")
        except Exception: pass
    except XenethAPIException as e:
        print(f"  open failed: {e}")
    finally:
        try:
            if cam.is_capturing: cam.stop_capture()
        except Exception: pass
        try: cam.close()
        except Exception: pass


def main():
    out_path = str(ROOT / "tools" / "probe_camera_full_props.txt")
    print("Dumping all properties…")
    dump_all_properties_to_file(out_path)

    urls = [
        "cam://0",
        "gev://169.254.133.25",      # the IP your Xeneth connection setup showed
        "cam://0?fg=XFrameGrabberNative",
    ]
    for u in urls:
        try_url(u)
    # one more pass with TLParamsLocked
    try_url("cam://0", with_tl_lock=True)


if __name__ == "__main__":
    main()

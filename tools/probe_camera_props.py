"""Dump camera properties (trigger / acquisition / cooling / etc.) and try
setting the ones that commonly stop a camera from streaming.

probe_camera.py confirmed: SDK opens fine, start_capture sets is_capturing
True, but get_frame times out after 10 s. That means the camera is "armed"
but not actually shipping frames. Most common cause on Bobcat-class cameras
is trigger mode being set to "external" (or whatever-non-FreeRunning).

This tool:
  1. Opens cam://0?fg=none for property access
  2. Lists ALL properties whose name contains trigger/acq/cool/run/frame/fps
  3. For each enum property, lists its valid range values
  4. Tries to set TriggerMode to internal/freerun-ish values

Run with Xeneth closed:
    uv run python tools/probe_camera_props.py
"""

import os, sys
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

from xenics.xeneth import XCamera
from xenics.xeneth.capi.enums import XPropType
from xenics.xeneth.errors import XenethAPIException


KEYWORDS = ["trigger", "acquisition", "acquire", "cool", "run", "frame",
            "fps", "rate", "mode", "ready", "fan", "tec", "stream"]


def main():
    cam = XCamera()
    cam.open("cam://0?fg=none")
    if not cam.is_initialized:
        print("not initialized"); return

    n = cam.get_property_count()
    print(f"{n} properties total\n")

    interesting = []
    for i in range(n):
        name = cam.get_property_name(i)
        if not any(k in name.lower() for k in KEYWORDS):
            continue
        try:
            ptype = cam.get_property_type(name)
            prange = cam.get_property_range(name)
            try:
                val = cam.get_property_value(name)
            except Exception as e:
                val = f"<read failed: {e}>"
            base = ptype & XPropType.XType_Base_Mask
            tname = {
                XPropType.XType_Base_Number: "Number",
                XPropType.XType_Base_Enum:   "Enum",
                XPropType.XType_Base_Bool:   "Bool",
                XPropType.XType_Base_String: "String",
                XPropType.XType_Base_Blob:   "Blob",
                XPropType.XType_Base_Action: "Action",
            }.get(base, str(ptype))
            print(f"  {name}")
            print(f"     type={tname}  range={prange}  value={val}")
            interesting.append((name, tname, prange, val))
        except Exception as e:
            print(f"  {name}: error {e}")

    print("\n--- looking for TriggerMode-style properties ---")
    for n, _, _, v in interesting:
        if "trigger" in n.lower() and "mode" in n.lower():
            print(f"  >>> {n} = {v}  <<<")

    cam.close()


if __name__ == "__main__":
    main()

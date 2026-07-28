# Xeneth SDK — DLL loading

## How it's wired (already resolved)

The camera needs two separate things, and they're handled in two different places:

| Part | What it is | Where it comes from |
|---|---|---|
| Python wrapper | the `xenics.xeneth` module | **vendored** in this repo at `lib/xenics/` |
| C runtime | `xeneth64.dll` and friends | the **Xeneth SDK installer** (`C:\Program Files\Common Files\XenICs\Runtime`) |

`gui/runtime.py` adds the runtime directory to the Windows DLL search path (via
`os.add_dll_directory`, plus `PATH`) at import time — before any driver loads.
That is why `main.py` imports `gui.runtime` first. Nothing else needs doing.

## If you get a DLL load error

1. **Is the SDK installed?** Launch `C:\Program Files\Xeneth\Xeneth64.exe`. If the
   GUI opens and sees the camera, the runtime is present — otherwise install the
   Xenics Xeneth SDK (see [LAB_SETUP.md](../LAB_SETUP.md)).
2. **Is the runtime where we look?** Confirm
   `C:\Program Files\Common Files\XenICs\Runtime` exists and contains
   `xeneth64.dll`. If the SDK installed it elsewhere, update `_XENETH_RUNTIME`
   in `gui/runtime.py`.
3. **Is Xeneth holding the camera?** Close it. The GigE stream has a single
   owner, so the app cannot connect while Xeneth has it open.

## Not a DLL problem

"Camera connects but no frames arrive" is **not** this issue — it is almost
always the Windows Firewall blocking inbound GigE stream packets. See
[GIGE_CAMERA_SETUP.md](GIGE_CAMERA_SETUP.md) and run
`tools/setup_lab_machine.ps1` as admin once per machine.

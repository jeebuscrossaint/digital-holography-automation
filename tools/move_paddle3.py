"""Absolute minimum: just move paddle 3.

If this moves paddle 3 and the GUI doesn't, the GUI is doing
something extra that breaks paddle 3 — and we know it's not the SDK
sequence itself.

Run with Kinesis closed:
    uv run python tools/move_paddle3.py 90
"""

import ctypes
import sys
import time

DLL    = r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"
SERIAL = b"38394984"

target = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0

lib = ctypes.cdll.LoadLibrary(DLL)
lib.TLI_BuildDeviceList()
if lib.MPC_Open(ctypes.c_char_p(SERIAL)) != 0:
    print("MPC_Open failed — is Kinesis still connected?")
    sys.exit(1)

try:
    lib.MPC_StartPolling(ctypes.c_char_p(SERIAL), ctypes.c_int(200))
    lib.MPC_RequestSettings(ctypes.c_char_p(SERIAL))
    time.sleep(0.5)
    lib.MPC_LoadSettings(ctypes.c_char_p(SERIAL))
    time.sleep(3.0)
    lib.MPC_ClearMessageQueue(ctypes.c_char_p(SERIAL))
    lib.MPC_SetEnabledPaddles(ctypes.c_char_p(SERIAL), ctypes.c_short(0x07))
    time.sleep(0.5)

    print(f"Moving paddle 3 to {target}°... watch it.")
    lib.MPC_MoveToPosition(ctypes.c_char_p(SERIAL),
                           ctypes.c_short(0x04),
                           ctypes.c_double(target))
    time.sleep(4)
    print("Done.")
finally:
    lib.MPC_StopPolling(ctypes.c_char_p(SERIAL))
    lib.MPC_Close(ctypes.c_char_p(SERIAL))

"""Literal copy of probe_mpc.py's talking-to-device section.

If probe_mpc.py moves paddle 3, this should too — it does the same
SDK calls in the same order. If THIS doesn't, the issue is something
even more subtle than the call sequence (which I'd be very surprised
by).

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
    print("MPC_Open failed")
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

    lib.MPC_GetEnabledPaddles.restype = ctypes.c_short
    e = lib.MPC_GetEnabledPaddles(ctypes.c_char_p(SERIAL))
    print(f"MPC_GetEnabledPaddles -> 0x{e:x}")

    lib.MPC_GetPosition.restype   = ctypes.c_double
    lib.MPC_GetStatusBits.restype = ctypes.c_uint

    print("Status + position for various paddle IDs:")
    for mask in (0x01, 0x02, 0x04, 0x08, 1, 2, 3, 4, 8):
        status = int(lib.MPC_GetStatusBits(ctypes.c_char_p(SERIAL), ctypes.c_short(mask)))
        pos    = float(lib.MPC_GetPosition(ctypes.c_char_p(SERIAL), ctypes.c_short(mask)))
        print(f"  ID 0x{mask:02x} ({mask:3d}): status=0x{status:08x}  pos={pos:7.2f}")

    before = [float(lib.MPC_GetPosition(ctypes.c_char_p(SERIAL), ctypes.c_short(m)))
              for m in (0x01, 0x02, 0x04)]
    print(f"  before: paddle1={before[0]:.2f}, paddle2={before[1]:.2f}, paddle3={before[2]:.2f}")

    # Send moves with the EXACT same IDs the probe uses. If paddle 3
    # moved during the probe, it'll move here.
    for trial in (0x04, 0x08, 3, 4):
        print(f"  -> MPC_MoveToPosition(id=0x{trial:02x}, {target}deg)")
        lib.MPC_MoveToPosition(ctypes.c_char_p(SERIAL),
                               ctypes.c_short(trial),
                               ctypes.c_double(target))
        time.sleep(2)
        after = [float(lib.MPC_GetPosition(ctypes.c_char_p(SERIAL), ctypes.c_short(m)))
                 for m in (0x01, 0x02, 0x04)]
        print(f"    after: paddle1={after[0]:.2f}, paddle2={after[1]:.2f}, paddle3={after[2]:.2f}")
finally:
    lib.MPC_StopPolling(ctypes.c_char_p(SERIAL))
    lib.MPC_Close(ctypes.c_char_p(SERIAL))

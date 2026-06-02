"""
Diagnostic probe for the Thorlabs MPC320 polarization controller.

What this prints:
  1. Which MPC_* symbols are exported by the installed Kinesis DLL.
  2. Status bits + reported position for paddle IDs 0x01, 0x02, 0x04
     (the documented bitmask) AND 1, 2, 3, 4, 8 (in case this firmware
     uses something different).
  3. The same query after explicitly calling MPC_EnableChannel for
     each paddle (if the symbol exists).

Run from the project root with Kinesis closed:
    uv run python tools/probe_mpc.py
"""

import ctypes
import sys
import time

DLL    = r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"
SERIAL = b"38394984"

CANDIDATES = """
MPC_Open MPC_Close MPC_StartPolling MPC_StopPolling MPC_PollingDuration
MPC_RequestSettings MPC_LoadSettings MPC_LoadNamedSettings MPC_PersistSettings
MPC_ClearMessageQueue MPC_RegisterMessageCallback
MPC_GetEnabledPaddles MPC_SetEnabledPaddles
MPC_EnableChannel MPC_DisableChannel
MPC_Identify MPC_GetHardwareInfo MPC_GetFirmwareVersion
MPC_GetStatusBits MPC_RequestStatusBits MPC_RequestStatus
MPC_GetPosition MPC_RequestPosition MPC_MoveToPosition
MPC_Home MPC_RequestHomingParams MPC_GetHomingParams MPC_SetHomingParams
MPC_GetJogParams MPC_SetJogParams MPC_GetMaxTravel
MPC_Stop MPC_StopProfiled MPC_StopImmediate
MPC_GetNumberPaddles MPC_GetPaddleConfig MPC_SetPaddleConfig
MPC_GetVelocity MPC_SetVelocity MPC_GetVelocityParams MPC_SetVelocityParams
MPC_RequestJogParams MPC_RequestVelocityParams
TLI_BuildDeviceList TLI_GetDeviceList
""".split()


def has(lib, name):
    try:
        getattr(lib, name)
        return True
    except AttributeError:
        return False


def main():
    lib = ctypes.cdll.LoadLibrary(DLL)
    print(f"Loaded: {DLL}")
    print()

    print("=" * 60)
    print("DLL exports")
    print("=" * 60)
    for name in CANDIDATES:
        print(("  YES  " if has(lib, name) else "  no   ") + name)
    print()

    print("=" * 60)
    print("Talking to device")
    print("=" * 60)
    lib.TLI_BuildDeviceList()
    if lib.MPC_Open(ctypes.c_char_p(SERIAL)) != 0:
        print("MPC_Open failed — close Kinesis first")
        sys.exit(1)

    try:
        lib.MPC_StartPolling(ctypes.c_char_p(SERIAL), ctypes.c_int(200))

        if has(lib, "MPC_RequestSettings"):
            lib.MPC_RequestSettings(ctypes.c_char_p(SERIAL))
            time.sleep(0.5)

        lib.MPC_LoadSettings(ctypes.c_char_p(SERIAL))
        time.sleep(3.0)

        lib.MPC_ClearMessageQueue(ctypes.c_char_p(SERIAL))
        lib.MPC_SetEnabledPaddles(ctypes.c_char_p(SERIAL), ctypes.c_short(0x07))
        time.sleep(0.5)

        if has(lib, "MPC_GetNumberPaddles"):
            lib.MPC_GetNumberPaddles.restype = ctypes.c_short
            n = lib.MPC_GetNumberPaddles(ctypes.c_char_p(SERIAL))
            print(f"MPC_GetNumberPaddles → {n}")

        if has(lib, "MPC_GetEnabledPaddles"):
            lib.MPC_GetEnabledPaddles.restype = ctypes.c_short
            e = lib.MPC_GetEnabledPaddles(ctypes.c_char_p(SERIAL))
            print(f"MPC_GetEnabledPaddles → 0x{e:x}")

        lib.MPC_GetPosition.restype    = ctypes.c_double
        lib.MPC_GetStatusBits.restype  = ctypes.c_uint

        print()
        print("Status + position for various paddle IDs:")
        for mask in (0x01, 0x02, 0x04, 0x08, 1, 2, 3, 4, 8):
            try:
                status = int(lib.MPC_GetStatusBits(ctypes.c_char_p(SERIAL), ctypes.c_short(mask)))
                pos    = float(lib.MPC_GetPosition(ctypes.c_char_p(SERIAL), ctypes.c_short(mask)))
                print(f"  ID 0x{mask:02x} ({mask:3d}): status=0x{status:08x}  pos={pos:7.2f}°")
            except Exception as e:
                print(f"  ID 0x{mask:02x}: error {e}")

        if has(lib, "MPC_EnableChannel"):
            print()
            print("Calling MPC_EnableChannel for paddle 1/2/3 bitmask values...")
            for mask in (0x01, 0x02, 0x04):
                lib.MPC_EnableChannel.restype = ctypes.c_short
                r = lib.MPC_EnableChannel(ctypes.c_char_p(SERIAL), ctypes.c_short(mask))
                print(f"  EnableChannel(0x{mask:02x}) → {r}")
            time.sleep(0.5)
            print("Status after EnableChannel:")
            for mask in (0x01, 0x02, 0x04):
                status = int(lib.MPC_GetStatusBits(ctypes.c_char_p(SERIAL), ctypes.c_short(mask)))
                pos    = float(lib.MPC_GetPosition(ctypes.c_char_p(SERIAL), ctypes.c_short(mask)))
                print(f"  ID 0x{mask:02x}: status=0x{status:08x}  pos={pos:.2f}°")

        # Sanity: try issuing a small move to paddle 3 with every plausible ID
        # and watch positions. Paddle 1 starts at ~80° from Kinesis-driven home.
        print()
        print("Probe-move test: send paddle-3-style move (target = current + 5°)")
        print("with each candidate ID, then see what (if anything) moved.")
        before = [float(lib.MPC_GetPosition(ctypes.c_char_p(SERIAL), ctypes.c_short(m)))
                  for m in (0x01, 0x02, 0x04)]
        print(f"  before: paddle1={before[0]:.2f}, paddle2={before[1]:.2f}, paddle3={before[2]:.2f}")
        for trial in (0x04, 0x08, 3, 4):
            target = 30.0 if before[2] < 50 else 100.0  # opposite of probable rest
            print(f"  → MPC_MoveToPosition(id=0x{trial:02x}, {target}°)")
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


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Thorlabs MPC320 driver — minimal, matches tools/probe_mpc.py exactly.

The probe successfully moved paddle 3 with a bare sequence:
    Open → StartPolling → RequestSettings → LoadSettings →
    ClearMessageQueue → SetEnabledPaddles → MoveToPosition

Anything extra (auto-home, auto-move-to-0, verify+retry on moveMotor)
breaks paddle 3 on this firmware. This module sticks to the
known-working sequence and exposes only single-shot commands.
"""

import ctypes
import os
import time

_DLL_PATH = r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"

# MPC SDK paddle enum (bitmask)
_PADDLE_BITS = {1: 0x01, 2: 0x02, 3: 0x04}
_ALL_PADDLES = 0x07

# Status bits
_STATUS_MOVING_CW  = 0x00000010
_STATUS_MOVING_CCW = 0x00000020
_STATUS_HOMING     = 0x00000200
_STATUS_HOMED      = 0x00000400
_BUSY_BITS         = _STATUS_MOVING_CW | _STATUS_MOVING_CCW | _STATUS_HOMING


class polMotors:
    """Bare-minimum MPC320 driver. Matches probe_mpc.py exactly."""

    def __init__(self, serialNumber=b"38394984"):
        kinesis_dir = os.path.dirname(_DLL_PATH)
        if os.path.isdir(kinesis_dir):
            try:
                os.add_dll_directory(kinesis_dir)
            except (AttributeError, OSError):
                pass
            os.environ["PATH"] = kinesis_dir + os.pathsep + os.environ.get("PATH", "")

        self.lib = ctypes.cdll.LoadLibrary(_DLL_PATH)
        # Only set return types — argument types stay default so ctypes
        # uses whatever we explicitly wrap with ctypes.c_short / c_double
        self.lib.MPC_Open.restype          = ctypes.c_short
        self.lib.MPC_Close.restype         = ctypes.c_short
        self.lib.MPC_GetPosition.restype   = ctypes.c_double
        self.lib.MPC_GetStatusBits.restype = ctypes.c_uint
        self.lib.MPC_GetMaxTravel.restype  = ctypes.c_double

        self.lib.TLI_BuildDeviceList()
        self._serial = serialNumber if isinstance(serialNumber, bytes) else str(serialNumber).encode()
        self.serialNumber = self._serial  # backward-compat attr

        if self.lib.MPC_Open(self._cp()) != 0:
            raise RuntimeError("MPC_Open failed")

        # The exact sequence the probe used to successfully move paddle 3
        self.lib.MPC_StartPolling(self._cp(), ctypes.c_int(200))
        try:
            self.lib.MPC_RequestSettings(self._cp())
        except Exception:
            pass
        time.sleep(0.5)
        self.lib.MPC_LoadSettings(self._cp())
        time.sleep(3.0)
        self.lib.MPC_ClearMessageQueue(self._cp())
        self.lib.MPC_SetEnabledPaddles(self._cp(), ctypes.c_short(_ALL_PADDLES))
        time.sleep(0.5)

        # The probe does ~9 GetStatusBits + GetPosition queries here
        # before the first move. THAT's what registers paddle 3 with
        # the polling thread — probe_mpc.py does these and moves
        # paddle 3, move_paddle3.py skips them and doesn't.
        for paddle in (1, 2, 3):
            bits = ctypes.c_short(_PADDLE_BITS[paddle])
            self.lib.MPC_GetStatusBits(self._cp(), bits)
            self.lib.MPC_GetPosition(self._cp(), bits)
            time.sleep(0.05)

        self.angles = [0.0, 0.0, 0.0]
        self._closed = False

    def _cp(self):
        """Fresh c_char_p of the serial — matches what the probe does."""
        return ctypes.c_char_p(self._serial)

    # ── single-shot commands (no retry, no verify) ─────────────────────────

    def moveMotor(self, motNum, angle):
        angle = float(angle)
        self.angles[motNum - 1] = angle

        # Big wake-up burst matching the probe exactly — same query masks
        # in the same order. probe_mpc.py does this and paddle 3 moves;
        # smaller wake-ups don't seem to be enough.
        for mask in (0x01, 0x02, 0x04, 0x08, 1, 2, 3, 4, 8):
            self.lib.MPC_GetStatusBits(self._cp(), ctypes.c_short(mask))
            self.lib.MPC_GetPosition(self._cp(),  ctypes.c_short(mask))

        bits = ctypes.c_short(_PADDLE_BITS[motNum])
        # Hammer the move command — paddle 3 sometimes ignores the first
        # one. Safe for paddles 1/2: re-issuing the same target is a no-op.
        for _ in range(4):
            self.lib.MPC_MoveToPosition(self._cp(), bits, ctypes.c_double(angle))
            time.sleep(0.5)

    def homeMotor(self, motNum):
        self.lib.MPC_Home(self._cp(), ctypes.c_short(_PADDLE_BITS[motNum]))

    def getPosition(self, motNum):
        return float(self.lib.MPC_GetPosition(self._cp(),
                                              ctypes.c_short(_PADDLE_BITS[motNum])))

    def _status(self, motNum):
        return int(self.lib.MPC_GetStatusBits(self._cp(),
                                              ctypes.c_short(_PADDLE_BITS[motNum])))

    def isHomed(self, motNum):
        return bool(self._status(motNum) & _STATUS_HOMED)

    def isBusy(self):
        time.sleep(0.01)
        for paddle in (1, 2, 3):
            if self._status(paddle) & _BUSY_BITS:
                return True
        return False

    def close(self):
        if self._closed:
            return
        try:
            self.lib.MPC_StopPolling(self._cp())
        except Exception:
            pass
        try:
            self.lib.MPC_Close(self._cp())
        except Exception:
            pass
        self._closed = True

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


if __name__ == '__main__':
    pm = polMotors()

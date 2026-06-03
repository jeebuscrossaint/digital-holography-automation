# -*- coding: utf-8 -*-
"""Thorlabs MPC320 driver.

Key gotcha discovered the hard way: the Kinesis MPC SDK uses
SEQUENTIAL paddle indices (1, 2, 3) for per-paddle operations like
MPC_Home / MPC_MoveToPosition / MPC_GetPosition / MPC_GetStatusBits.
NOT the bitmask values from the MPC_Paddles enum (0x01, 0x02, 0x04).

MPC_SetEnabledPaddles is the only call that takes a bitmask
(0x07 = all three enabled).

Confirmed by probe: MPC_GetPosition with mask=3 returns paddle 3's
real position; with mask=0x04 it returns garbage zero.
"""

import ctypes
import os
import time
from pathlib import Path


def _resolve_dll() -> str:
    """Prefer the vendored Thorlabs DLLs (so lab members don't have to
    install Kinesis), fall back to the system install path."""
    here = Path(__file__).resolve().parent.parent
    vendored = here / "vendor" / "thorlabs" / "Thorlabs.MotionControl.Polarizer.dll"
    if vendored.exists():
        return str(vendored)
    return r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"


_DLL_PATH = _resolve_dll()

# Per-paddle SDK identifier (NOT a bitmask)
_PADDLE_ID   = {1: 1, 2: 2, 3: 3}
# Bitmask only for SetEnabledPaddles
_ALL_PADDLES = 0x07

# Status word bits
_STATUS_MOVING_CW  = 0x00000010
_STATUS_MOVING_CCW = 0x00000020
_STATUS_HOMING     = 0x00000200
_STATUS_HOMED      = 0x00000400
_BUSY_BITS         = _STATUS_MOVING_CW | _STATUS_MOVING_CCW | _STATUS_HOMING


class polMotors:
    def __init__(self, serialNumber=b"38394984"):
        kinesis_dir = os.path.dirname(_DLL_PATH)
        if os.path.isdir(kinesis_dir):
            try:
                os.add_dll_directory(kinesis_dir)
            except (AttributeError, OSError):
                pass
            os.environ["PATH"] = kinesis_dir + os.pathsep + os.environ.get("PATH", "")

        self.lib = ctypes.cdll.LoadLibrary(_DLL_PATH)
        self.lib.MPC_Open.restype          = ctypes.c_short
        self.lib.MPC_Close.restype         = ctypes.c_short
        self.lib.MPC_GetPosition.restype   = ctypes.c_double
        self.lib.MPC_GetStatusBits.restype = ctypes.c_uint
        self.lib.MPC_GetMaxTravel.restype  = ctypes.c_double

        self.lib.TLI_BuildDeviceList()
        self._serial = serialNumber if isinstance(serialNumber, bytes) else str(serialNumber).encode()
        self.serialNumber = self._serial

        if self.lib.MPC_Open(self._cp()) != 0:
            raise RuntimeError("MPC_Open failed")

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

        self.angles = [0.0, 0.0, 0.0]
        self._closed = False

    def _cp(self):
        return ctypes.c_char_p(self._serial)

    def moveMotor(self, motNum, angle):
        angle = float(angle)
        self.angles[motNum - 1] = angle
        self.lib.MPC_MoveToPosition(self._cp(),
                                    ctypes.c_short(_PADDLE_ID[motNum]),
                                    ctypes.c_double(angle))

    def homeMotor(self, motNum):
        self.lib.MPC_Home(self._cp(), ctypes.c_short(_PADDLE_ID[motNum]))

    def getPosition(self, motNum):
        return float(self.lib.MPC_GetPosition(self._cp(),
                                              ctypes.c_short(_PADDLE_ID[motNum])))

    def _status(self, motNum):
        return int(self.lib.MPC_GetStatusBits(self._cp(),
                                              ctypes.c_short(_PADDLE_ID[motNum])))

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

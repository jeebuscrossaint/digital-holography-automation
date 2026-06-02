# -*- coding: utf-8 -*-
import ctypes
import os
import time

_DLL_PATH = r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"

# Thorlabs MPC SDK: paddles are addressed by a single-bit mask, not by index
_PADDLE_BITS = {1: 0x01, 2: 0x02, 3: 0x04}
_ALL_PADDLES = 0x07

# Status word bits we care about
_STATUS_MOVING_CW  = 0x00000010   # bit 4
_STATUS_MOVING_CCW = 0x00000020   # bit 5
_STATUS_HOMING     = 0x00000200   # bit 9
_STATUS_HOMED      = 0x00000400   # bit 10
_BUSY_BITS         = _STATUS_MOVING_CW | _STATUS_MOVING_CCW | _STATUS_HOMING


def _check(name, code):
    if code != 0:
        raise RuntimeError(f"{name} returned Kinesis error code {code}")


class polMotors:  # max travel 160°
    def __init__(self, serialNumber=b"38394984"):
        # Let Windows find the Kinesis support DLLs next to the polarizer DLL
        kinesis_dir = os.path.dirname(_DLL_PATH)
        if os.path.isdir(kinesis_dir):
            try:
                os.add_dll_directory(kinesis_dir)
            except (AttributeError, OSError):
                pass
            os.environ["PATH"] = kinesis_dir + os.pathsep + os.environ.get("PATH", "")

        self.lib = ctypes.cdll.LoadLibrary(_DLL_PATH)
        self._setup_signatures()
        self.lib.TLI_BuildDeviceList()

        # Keep the bytes alive — ctypes auto-converts to c_char_p with argtypes set
        self.serialNumber = (serialNumber if isinstance(serialNumber, bytes)
                             else str(serialNumber).encode())

        _check("MPC_Open", self.lib.MPC_Open(self.serialNumber))

        if not self.lib.MPC_StartPolling(self.serialNumber, 200):
            raise RuntimeError("MPC_StartPolling failed")

        # Settings must be loaded before the controller will accept moves /
        # individual homing — otherwise MPC_Home returns code 43 (no motor info)
        self.lib.MPC_LoadSettings(self.serialNumber)
        time.sleep(2.5)

        self.lib.MPC_ClearMessageQueue(self.serialNumber)

        # Enable each paddle in its own call before the AllPaddles call.
        # On some MPC firmware / USB-hub setups, a single AllPaddles
        # enable call doesn't propagate to all three paddles (paddle 3
        # ends up with status 0x0 = nothing reported).
        for paddle in (1, 2, 3):
            self.lib.MPC_SetEnabledPaddles(self.serialNumber, _PADDLE_BITS[paddle])
            time.sleep(0.05)
        self.lib.MPC_SetEnabledPaddles(self.serialNumber, _ALL_PADDLES)
        time.sleep(0.1)

        # Home each paddle individually. MPC_Home routinely returns code 43
        # (MOT_NoMotorInfo) even when the move actually queues and the
        # paddle physically rotates — don't trust the return code, just
        # wait for motion to settle.
        for paddle in (1, 2, 3):
            code = self.lib.MPC_Home(self.serialNumber, _PADDLE_BITS[paddle])
            if code != 0:
                print(f"  MPC_Home paddle {paddle} returned code {code} (often spurious)")

        # Wait for any homing motion to finish — up to 30 s.
        deadline = time.time() + 30
        while time.time() < deadline and self.isBusy():
            time.sleep(0.2)

        self.angles = [0.0, 0.0, 0.0]
        self._closed = False

    def _setup_signatures(self):
        """Tell ctypes the exact argument and return types for every call.
        Without this, ctypes guesses (default int return, no argument
        checking) and the x64 calling convention can mis-place the double
        position argument."""
        L = self.lib
        L.TLI_BuildDeviceList.restype     = ctypes.c_short
        L.MPC_Open.argtypes               = [ctypes.c_char_p]
        L.MPC_Open.restype                = ctypes.c_short
        L.MPC_Close.argtypes              = [ctypes.c_char_p]
        L.MPC_Close.restype               = ctypes.c_short
        L.MPC_StartPolling.argtypes       = [ctypes.c_char_p, ctypes.c_int]
        L.MPC_StartPolling.restype        = ctypes.c_bool
        L.MPC_StopPolling.argtypes        = [ctypes.c_char_p]
        L.MPC_StopPolling.restype         = None
        L.MPC_ClearMessageQueue.argtypes  = [ctypes.c_char_p]
        L.MPC_ClearMessageQueue.restype   = None
        L.MPC_LoadSettings.argtypes       = [ctypes.c_char_p]
        L.MPC_LoadSettings.restype        = ctypes.c_bool
        L.MPC_SetEnabledPaddles.argtypes  = [ctypes.c_char_p, ctypes.c_short]
        L.MPC_SetEnabledPaddles.restype   = ctypes.c_short
        L.MPC_Home.argtypes               = [ctypes.c_char_p, ctypes.c_short]
        L.MPC_Home.restype                = ctypes.c_short
        L.MPC_MoveToPosition.argtypes     = [ctypes.c_char_p, ctypes.c_short, ctypes.c_double]
        L.MPC_MoveToPosition.restype      = ctypes.c_short
        L.MPC_GetPosition.argtypes        = [ctypes.c_char_p, ctypes.c_short]
        L.MPC_GetPosition.restype         = ctypes.c_double
        L.MPC_GetStatusBits.argtypes      = [ctypes.c_char_p, ctypes.c_short]
        L.MPC_GetStatusBits.restype       = ctypes.c_uint
        L.MPC_GetMaxTravel.argtypes       = [ctypes.c_char_p]
        L.MPC_GetMaxTravel.restype        = ctypes.c_double

    def _status(self, motNum):
        return int(self.lib.MPC_GetStatusBits(self.serialNumber, _PADDLE_BITS[motNum]))

    def moveMotor(self, motNum, angle):
        angle = float(angle)
        self.angles[motNum - 1] = angle
        code = self.lib.MPC_MoveToPosition(self.serialNumber,
                                           _PADDLE_BITS[motNum], angle)
        if code != 0:
            # SDK fibs — the move often physically executes anyway. Log so
            # we can see it, but don't refuse the operation.
            print(f"  MPC_MoveToPosition paddle {motNum} → {angle:.1f}° returned {code}")

    def getPosition(self, motNum):
        return float(self.lib.MPC_GetPosition(self.serialNumber,
                                              _PADDLE_BITS[motNum]))

    def homeMotor(self, motNum):
        code = self.lib.MPC_Home(self.serialNumber, _PADDLE_BITS[motNum])
        if code != 0:
            print(f"  MPC_Home paddle {motNum} returned {code}")

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
            self.lib.MPC_StopPolling(self.serialNumber)
        except Exception:
            pass
        try:
            self.lib.MPC_Close(self.serialNumber)
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

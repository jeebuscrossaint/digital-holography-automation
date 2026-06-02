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

        self.lib.MPC_StartPolling(self.serialNumber, 50)

        # Some MPC firmware needs an explicit RequestSettings handshake
        # before LoadSettings, otherwise the polling thread doesn't
        # populate the per-paddle status cache for every paddle.
        self._call_optional("MPC_RequestSettings", self.serialNumber)
        time.sleep(0.3)

        self.lib.MPC_LoadSettings(self.serialNumber)
        time.sleep(3.0)

        self.lib.MPC_ClearMessageQueue(self.serialNumber)
        self.lib.MPC_SetEnabledPaddles(self.serialNumber, _ALL_PADDLES)
        time.sleep(0.2)

        # Speculative: some MPC SDK versions need a per-paddle channel enable
        # in addition to SetEnabledPaddles. If present in the DLL, call it.
        for paddle in (1, 2, 3):
            self._call_optional("MPC_EnableChannel", self.serialNumber, _PADDLE_BITS[paddle])
            time.sleep(0.05)

        # Wake each paddle's status cache. Without these calls the polling
        # thread leaves paddle 3 at status=0x0 forever even though it's
        # physically present and Kinesis can drive it.
        for paddle in (1, 2, 3):
            self._call_optional("MPC_RequestStatusBits", self.serialNumber, _PADDLE_BITS[paddle])
            self._call_optional("MPC_RequestStatus",     self.serialNumber, _PADDLE_BITS[paddle])
            self._call_optional("MPC_RequestPosition",   self.serialNumber, _PADDLE_BITS[paddle])
            time.sleep(0.1)

        # MPC_Home routinely returns code 43 (MOT_NoMotorInfo) even when
        # the move actually queues and the paddle physically rotates —
        # don't trust the return code.
        for paddle in (1, 2, 3):
            code = self.lib.MPC_Home(self.serialNumber, _PADDLE_BITS[paddle])
            if code != 0:
                print(f"  MPC_Home paddle {paddle} returned code {code} (often spurious)")

        # Ramp polling up to a tighter cadence now that the device is up
        self.lib.MPC_StartPolling(self.serialNumber, 200)

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

    def _call_optional(self, name, *args):
        """Try to call a Kinesis function that may not exist in every SDK
        version. Returns None on missing symbol or call failure."""
        try:
            fn = getattr(self.lib, name)
        except AttributeError:
            return None
        # Set conservative argtypes if we know the shape
        if len(args) == 1:
            fn.argtypes = [ctypes.c_char_p]
            fn.restype  = ctypes.c_short
        elif len(args) == 2:
            fn.argtypes = [ctypes.c_char_p, ctypes.c_short]
            fn.restype  = ctypes.c_short
        try:
            return fn(*args)
        except Exception:
            return None

    def moveMotor(self, motNum, angle):
        angle = float(angle)
        self.angles[motNum - 1] = angle
        start = self.getPosition(motNum)

        for attempt in (0, 1):
            code = self.lib.MPC_MoveToPosition(self.serialNumber,
                                               _PADDLE_BITS[motNum], angle)
            if code != 0:
                print(f"  MPC_MoveToPosition paddle {motNum} → {angle:.1f}° returned {code}")

            # If the paddle was already at target, no motion expected
            if abs(angle - start) < 0.3:
                return

            # Did motion actually start? Sample after one polling cycle
            time.sleep(0.35)
            if abs(self.getPosition(motNum) - start) > 0.1:
                return

            if attempt == 0:
                # First command got swallowed — retry once after a short pause
                print(f"  Paddle {motNum} ignored move command, retrying once")
                time.sleep(0.15)

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

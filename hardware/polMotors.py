# -*- coding: utf-8 -*-
import ctypes
import time

_DLL_PATH = r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"

# Thorlabs MPC SDK paddle enum: each paddle is a single bit, not an index
_PADDLE_BITS = {1: 0x01, 2: 0x02, 3: 0x04}
_ALL_PADDLES = 0x07


class polMotors:  # max travel for this is 160 deg
    def __init__(self, serialNumber=b"38394984"):
        self.lib = ctypes.cdll.LoadLibrary(_DLL_PATH)
        self.lib.TLI_BuildDeviceList()
        serialNumber = ctypes.c_char_p(serialNumber)

        self.lib.MPC_Open(serialNumber)
        self.lib.MPC_StartPolling(serialNumber, ctypes.c_int(50))
        self.lib.MPC_LoadSettings(serialNumber)
        time.sleep(3)
        self.lib.MPC_ClearMessageQueue(serialNumber)
        self.lib.MPC_SetEnabledPaddles(serialNumber, ctypes.c_short(_ALL_PADDLES))
        self.lib.MPC_GetMaxTravel.restype = ctypes.c_double
        for paddle in (1, 2, 3):
            self.lib.MPC_Home(serialNumber, ctypes.c_short(_PADDLE_BITS[paddle]))
        self.lib.MPC_StartPolling(serialNumber, ctypes.c_int(200))

        self.serialNumber = serialNumber
        self.angles = [0, 0, 0]
        self._closed = False

    def moveMotor(self, motNum, angle):
        self.angles[motNum - 1] = float(angle)
        self.lib.MPC_MoveToPosition(self.serialNumber,
                                    ctypes.c_short(_PADDLE_BITS[motNum]),
                                    ctypes.c_double(float(angle)))

    def getPosition(self, motNum):
        self.lib.MPC_GetPosition.restype = ctypes.c_double
        return float(self.lib.MPC_GetPosition(self.serialNumber,
                                              ctypes.c_short(_PADDLE_BITS[motNum])))

    def homeMotor(self, motNum):
        self.lib.MPC_Home(self.serialNumber, ctypes.c_short(_PADDLE_BITS[motNum]))

    def isBusy(self):
        time.sleep(0.01)
        for paddle in (1, 2, 3):
            bits = self.lib.MPC_GetStatusBits(self.serialNumber,
                                              ctypes.c_short(_PADDLE_BITS[paddle])) & 0xFF
            if bits != 0:
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

# -*- coding: utf-8 -*-
import ctypes
import time

_DLL_PATH = r"C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll"


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
        for paddle in (1, 2, 3, 7):
            self.lib.MPC_SetEnabledPaddles(serialNumber, paddle)
        self.lib.MPC_GetMaxTravel.restype = ctypes.c_double
        for paddle in (1, 2, 3):
            self.lib.MPC_Home(serialNumber, paddle)
        self.lib.MPC_StartPolling(serialNumber, ctypes.c_int(200))

        self.serialNumber = serialNumber
        self.angles = [0, 0, 0]
        self._closed = False

    def moveMotor(self, motNum, angle):  # paddles are 1, 2, 3
        self.angles[motNum - 1] = angle
        self.lib.MPC_MoveToPosition(self.serialNumber, motNum, ctypes.c_double(angle))

    def isBusy(self):
        time.sleep(0.01)
        a = self.lib.MPC_GetStatusBits(self.serialNumber, ctypes.c_int(1)) & 0xFF
        b = self.lib.MPC_GetStatusBits(self.serialNumber, ctypes.c_int(2)) & 0xFF
        c = self.lib.MPC_GetStatusBits(self.serialNumber, ctypes.c_int(3)) & 0xFF
        return not (a == 0 and b == 0 and c == 0)

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

# -*- coding: utf-8 -*-
"""
Created on Tue Oct 14 20:54:53 2025

@author: mecdm
"""

import os
import ctypes
import time


class polMotors: #max travel for this is 160 deg
    def __init__(self, serialNumber = b"38394984"):
        #maybe this path should be a default variable but I'm lazy
        self.lib = ctypes.cdll.LoadLibrary("C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Polarizer.dll")
        self.lib.TLI_BuildDeviceList()
        #Set up Serial Number variable
        serialNumber = ctypes.c_char_p(serialNumber)
        #Set up Device and Enable the Channel
        self.lib.MPC_Open(serialNumber)
        self.lib.MPC_StartPolling(serialNumber, ctypes.c_int(50))
        self.lib.MPC_LoadSettings(serialNumber)
        time.sleep(3)
        self.lib.MPC_ClearMessageQueue(serialNumber)
        self.lib.MPC_SetEnabledPaddles(serialNumber, 1)
        self.lib.MPC_SetEnabledPaddles(serialNumber, 2)
        self.lib.MPC_SetEnabledPaddles(serialNumber, 3)
        self.lib.MPC_SetEnabledPaddles(serialNumber, 7)
        self.lib.MPC_GetMaxTravel.restype = ctypes.c_double
        self.lib.MPC_Home(serialNumber, 1)
        self.lib.MPC_Home(serialNumber, 2)
        self.lib.MPC_Home(serialNumber, 3)
        self.lib.MPC_StartPolling(serialNumber,200)
        
        self.serialNumber = serialNumber
        self.angles = [0,0,0]
        
    
    def moveMotor(self, motNum, angle): #motors are 1 2 and 3.  Idk why not 0, 1, and 2,
        self.angles[motNum-1] = angle
        self.lib.MPC_MoveToPosition(self.serialNumber, motNum, ctypes.c_double(angle))
        
    def isBusy(self):
        time.sleep(.01)
        a = self.lib.MPC_GetStatusBits(self.serialNumber,ctypes.c_int(1)) & 0xFF #mask to see if there's movement   
        b = self.lib.MPC_GetStatusBits(self.serialNumber,ctypes.c_int(2)) & 0xFF 
        c = self.lib.MPC_GetStatusBits(self.serialNumber,ctypes.c_int(3)) & 0xFF
        if (a == 0 and b == 0 and c == 0):
            return False
        else:
            return True
        
if __name__ == '__main__':
    pm = polMotors()
        
        
        
        
        
        
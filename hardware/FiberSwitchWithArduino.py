# -*- coding: utf-8 -*-
"""
Created on Wed Oct  8 15:05:45 2025

@author: ca109683
"""

# fiberSwitch.py
import time
import serial  
class fiberSwitch:
    def __init__(self, port: str = "COM3",timeout = 1):
        #Be sure to check the COM Port
        
        try:
            self.switch = serial.Serial(port, timeout=timeout)
            print(f"[INFO] Fiber switch connected on {port}")
            
        except Exception as e:
            print(f"[ERROR] Could not connect to port {port}: {e}")
            
    def info(self) -> str: #returns device ID
        self.switch.reset_input_buffer()
        self.switch.write("ID?".encode())
        time.sleep(.1)  #idk why I need this
        data = b''
        while True:
            a = self.switch.read(1)
            if a:
                data += a
            else:
                break
        print(data)
        
        
    def setChannel(self,channel): 
        self.switch.reset_input_buffer()
        string = "i1 " + str(channel)
        self.switch.write(string.encode())
       
        

    def getChannel(self):
        self.switch.reset_input_buffer()
        self.switch.write("i1?".encode())
        time.sleep(.1)#idk why I needthis 
        a = self.switch.read(2)
        return a.decode()
        
    
    def park(self):
        self.switch.reset_input_buffer()
        self.switch.write("pk".encode())
        
        
    def close(self):
        self.switch.close()
        
    def __del__(self): #idk if this works how I expect
        try:
            self.switch.close()
            print("Serial connection closed in __del__")
        except:
            pass
        
if __name__ == '__main__':
    switch = fiberSwitch()
    print(switch.info())
        


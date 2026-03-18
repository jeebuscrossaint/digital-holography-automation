# -*- coding: utf-8 -*-
"""
Created on Tue Oct 14 22:49:52 2025

Thorlabs Power Meter Reader

You need the legacy sofware to run this, I think
https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=PM100x

tip, you can list resources using the following code
The PM will follow the convention USB0::0x1313::0x8078::serial#::0::INSTR

import pyvisa as visa
rm = visa.ResourceManager()
print(rm.list_resources())

#there's a ton of functions but I can't be bothered to add them
-change wavelength
-sample rate
-change unit


This is bad code, and I am lazy

-Caleb.
"""



import pyvisa as visa
from ThorlabsPM100 import ThorlabsPM100

class tlpm:
    def __init__(self,address='USB0::0x1313::0x8078::P0003991::0::INSTR'):
        rm = visa.ResourceManager();
        self.inst = rm.open_resource(address,read_termination='\n');
        self.pmeter = ThorlabsPM100(inst=self.inst);
        self.pmeter.sense.average.count = 500;
    def read(self):
        return self.pmeter.read
# -*- coding: utf-8 -*-
"""
Created on Thu Nov 11 20:37:56 2021

@author: ca109683
"""

#import ivi
import pyvisa as visa
import matplotlib.pyplot as plt
import numpy as np
import time


class HPTunableLaserSource:
    def __init__(self, TLName = 'GPIB0::24::INSTR'):
        rm = visa.ResourceManager()
        print(rm.list_resources())
        try:
            self.TL = rm.open_resource(TLName)
        except:
            print("itwasopen")
            self.TL.close() #in case the TL wasn't closed at the end of the last session
            
            self.TL = rm.open_resource('TLName')
        
    def outputState(self,tf):  #1 is on, 0 is off
        if tf:
            self.TL.write(":OUTP:STAT 1")
        else:
            self.TL.write(":OUTP:STAT 0")
                
    def isOutputOn(self):
        return self.TL.query(":OUTP:STAT?") 

    def powerAmplitude(self,num): #number may be in from -10dBm to -4dBm or 100uW to 398uW.  Alt, use MIN, DEF, MAX
    #assign units as DBM, DBMW, PW, NW, UW, MW, or W
        self.TL.write(":POW " + str(num))
    
    def checkPowerAmplitude(self,string = ''): #string = MIN, MAX, DEF will return min power, max power, or default
        return(self.TL.query(":POW? " + str(string)))
    
    def changePowerUnit(self,string):
        self.TL.write(":POW:UNIT " + str(string))
        
    def checkPowerUnit(self):
        return(self.TL.query(":POW:UNIT?"))
    
    def changeWavelength(self,num):# also work swith MIN, MAX, DEF, in our case the 8168E machine is 1475, 1575, 1540 nm
        self.TL.write(":WAVE " + str(num))
    
    def checkWavelength(self,string = ''): #can work with MIN, MAX, DEF
        return(self.TL.query(":WAVE? " + str(string)))
    
    def checkWavelengthReference(self):
        return(self.TL.query(":WAVE:REF?"))
    
    def setReferenceWavelength(self): #sets reference wavelength to current wavelength
        self.TL.write("WAVE:REF:DISP")
        

        #less useful functions down here
            
        
    def displayEnable(self,tF): #1 is on, 0 is off
        if tF:
            self.TL.write(":DISP:ENAB 1")
        else:
            self.TL.write(":DISP:ENAB 0")
    
    def isDisplayOn(self):
        return self.TL.query(":DISP:ENAB?")
        
    def clearStatus(self):
        self.TL.write("*CLS")
            
    def setAmplitudeFrequency(self,freq): #set between 250Hz and 300kHz
        self.TL.write(":SOUR:AM:INT:FREQ " + str(freq))
            
    def whatAmplitudeFrequeny(self):
        return self.TL.query(":SOUR:AM:INT:FREQ?")
    
    def typeOfModulation(self,num): #0 for internal modulation, 1 coherent control, 2 external modulation
        self.TL.write(":SOUR:AM:SOUR " + str(num))
        
    def whatTypeOfModulation(self): #0 for internal modulation, 1 coherent control, 2 external modulation
        return self.TL.query(":SOUR:AM:SOUR?")
    
    def modulationState(self,tf): # 0 for modulatin off, 1 for modulation on
        if tf:
            self.TL.write(":SOUR:AM:STAT 1")
        else:
            self.TL.write(":SOUR:AM:STAT 0")
            
    def modulationType(self,tf): #0 for constant modulation, 1 for low when signal is being changed
        if tf:
            self.TL.write(":SOURCE:MODOUT 0")
        else:
           self. TL.write(":SOURCE:MODOUT 1")
    
    def setFrequencyOffset(self, num):#set in HZ, megahertz I think is spelled MAHZ for some reason
        self.TL.write("WAVE:FREQ " + str(num))
    
    def checkFrequenyOffset(self):
        return(self.TL.query(":WAVE:FREQ?"))
    
    def checkLaserCondition(self): #bit 8 is 1 when output power is larger than laser can produce, bit9 is 1 during power up
        return(":STAT:OPER:COND?")
    
    def closeConnection(self):
        self.TL.close()
        
    def __del__(self): #idk if this works how I expect
        try:
            self.TL.close()
            print("Serial connection closed in __del__")
        except:
            pass


#%%ask TL for outputs

# ID = TL.query("*IDN?")
# outputState(True)
# print(ID)




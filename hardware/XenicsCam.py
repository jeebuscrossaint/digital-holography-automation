#This works specifically an exclusively for the Orange Bobcat#
import sys
from datetime import datetime
from xenics.xeneth import *
from xenics.xeneth.errors import XenethAPIException, XenethException
from xenics.xeneth.xcamera import XCamera

"""
Discovers available cameras and prompts for selection if necessary
"""
def dev_discovery():

    # enumerate all
    flags = XEnumerationFlags.XEF_EnableAll
    val = 0
    try:
        # enumerate devices
        devices = enumerate_devices(flags)

        if len(devices) == 0:
            print("No devices found")
            sys.exit()

        states = {XDeviceStates.XDS_Available : "Available",
                XDeviceStates.XDS_Busy : "Busy",
                XDeviceStates.XDS_Unreachable : "Unreachable"}

        for idx, dev in enumerate(devices):
            print(f"Device[{idx}] {dev.name} @ {dev.address} ({dev.transport})")
            print(f"PID: {dev.pid}")
            print(f"Serial: {dev.serial}")
            print(f"URL: {dev.url}")
            print(f"State: {states[dev.state]} ({dev.state})\n")

        if idx > 1:
            val = input("Enter desired device number")
            val = int(val)
            if idx > 1:
                while True:
                    try:
                        val = int(input("Enter desired device number: "))
                        if val <= idx:
                            break
                        else:
                            print(f"Please enter a number less than or equal to {idx}.")
                    except ValueError:
                        print("Invalid input. Please enter a valid integer.")

    except XenethException as e:
        print(f"Error occurred during device discovery: {e.message}")

    return devices[val].url

class xCam:
    def __init__(self, url=None):
        self.cam = XCamera()
        if not url:
            url = dev_discover()

        # open camera and start capturing
        try:
            # url example: url = "cam://0?fg=none"
            print(f"Opening connection to {url}")
            self.cam.open(url)
            if self.cam.is_initialized:
                self.pid = self.cam.get_property_value("_CAM_PID")
                self.ser = self.cam.get_property_value("_CAM_SER")
                try:
                    self.exposure_time = self.cam.get_property_value("ExposureTime")
                except Exception:
                    self.exposure_time = 500.0  # default if property unavailable
                # Output the product id and serial and exposure time
                print(f"Controlling camera with PID: 0x{int(self.pid):X}, SER: {self.ser}, ExposureTime: {self.exposure_time}")
            
            # Try to load calibration, but don't fail if missing
            try:
                import os as _os
                _cal = _os.path.join(_os.path.dirname(__file__), 'calibration', 'XC-(10-06-2021)-500us_14931.xca')
                self.cam.load_calibration(_cal, 2)
            except Exception as e:
                print(f"Calibration file not found (this is OK, will use default): {e}")
            
            self.buffer = self.cam.create_buffer()
            if self.cam.is_initialized:
                print("Start capturing")
                self.cam.start_capture()
            else:
                print("Initialization failed")
    
        except XenethAPIException as e:
            print(e.message)
    def getFrame(self):
        if self.cam.get_frame(self.buffer, flags=XGetFrameFlags.XGF_Blocking):
            return self.buffer.image_data
        
    def stopCapture(self):
        self.cam.stop_capture()
        
    def closeCamera(self):
        self.cam.close()

    def __del__(self): #idk if this works how I expect
        if self.cam.is_capturing:
            try:
                print("Stop capturing")
                self.cam.stop_capture()
                print("Close Camera")
                self.cam.close()
            except XenethAPIException as e:
                print(e.message)
                    
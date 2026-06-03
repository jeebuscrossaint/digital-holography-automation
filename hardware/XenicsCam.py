#This works specifically an exclusively for the Orange Bobcat#
import sys
from datetime import datetime
import time
from xenics.xeneth import *
from xenics.xeneth.errors import XenethAPIException, XenethException
from xenics.xeneth.xcamera import XCamera
from xenics.xeneth.capi.enums import XLoadCalibrationFlags

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
            url = dev_discovery()

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
            
            # Calibration is OPTIONAL. The previous code passed flag=2
            # which is XLC_RFU_1 (reserved / undefined) — likely the
            # reason every frame came back as zeros. Skip calibration
            # by default; enable via env var XENETH_LOAD_CAL=1 with the
            # CORRECT flag (XLC_StartSoftwareCorrection = 1).
            import os as _os
            if _os.environ.get("XENETH_LOAD_CAL") == "1":
                try:
                    _cal = _os.path.join(_os.path.dirname(__file__),
                                         'calibration',
                                         'XC-(10-06-2021)-500us_14931.xca')
                    self.cam.load_calibration(
                        _cal, XLoadCalibrationFlags.XLC_StartSoftwareCorrection)
                    print(f"Calibration loaded: {_cal}")
                except Exception as e:
                    print(f"Calibration not loaded (continuing without): {e}")

            self.buffer = self.cam.create_buffer()
            if self.cam.is_initialized:
                print("Start capturing")
                self.cam.start_capture()
                # Discard the first few frames — the sensor & DMA pipeline
                # need a moment to flush after StartCapture
                time.sleep(0.2)
                for _ in range(3):
                    try:
                        self.cam.get_frame(self.buffer, flags=XGetFrameFlags.XGF_Blocking)
                    except Exception:
                        break
            else:
                print("Initialization failed")

        except XenethAPIException as e:
            print(e.message)
        self._closed = False

    def getFrame(self):
        if self.cam.get_frame(self.buffer, flags=XGetFrameFlags.XGF_Blocking):
            return self.buffer.image_data

    def stopCapture(self):
        if self._closed:
            return
        try:
            if self.cam.is_capturing:
                self.cam.stop_capture()
        except Exception:
            pass

    def closeCamera(self):
        if self._closed:
            return
        try:
            if self.cam.is_capturing:
                try:
                    self.cam.stop_capture()
                except Exception:
                    pass
            self.cam.close()
        except Exception:
            pass
        self._closed = True

    def __del__(self):
        try:
            self.closeCamera()
        except Exception:
            pass
                    
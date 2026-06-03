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
            
            # The camera returns all-zero frames when no calibration is
            # loaded — confirmed empirically against a lab mate's working
            # version of this driver. Always load the cal file. Pick the
            # one matching the current exposure (we ship 500 / 1000 /
            # 5000 / 10000 µs variants) and fall back to 500 µs.
            import os as _os
            cal_dir = _os.path.join(_os.path.dirname(__file__), 'calibration')
            sys_cal_dir = r"C:\Program Files\Xeneth\Calibrations"
            exp_us = int(round(float(self.exposure_time)))
            choices = [exp_us, 500, 1000, 5000, 10000]
            cal_path = None
            for us in choices:
                for d in (cal_dir, sys_cal_dir):
                    p = _os.path.join(d, f"XC-(10-06-2021)-{us}us_14931.xca")
                    if _os.path.exists(p):
                        cal_path = p; break
                if cal_path: break
            if cal_path:
                # flag=2 is what the lab mate's working code uses; the
                # enum file labels it RFU_1 but the SDK accepts it.
                try:
                    self.cam.load_calibration(cal_path, 2)
                    print(f"Calibration loaded: {cal_path}")
                except Exception as e:
                    print(f"Calibration load FAILED ({cal_path}): {e}")
            else:
                print("No calibration file found — camera will likely return zero frames")

            self.buffer = self.cam.create_buffer()
            if self.cam.is_initialized:
                print("Start capturing")
                self.cam.start_capture()
                # Brief warmup so the first user-visible frame is real
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
                    
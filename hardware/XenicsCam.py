#This works specifically an exclusively for the Orange Bobcat#
import sys
from datetime import datetime
import os
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

def pick_real_camera_url() -> str:
    """Enumerate cameras, skip the Virtual camera (serial 0), return the
    URL of the first real one. Falls back to "cam://0" if enumeration
    fails entirely.

    Per Xeneth SDK docs:
      - `cam://N` picks device by index (might land on the Virtual cam)
      - `?fg=none` puts the API in command-and-control mode with NO
        framegrabbing (which is why our frames were all zeros)
      - omitting fg uses the native framegrabber, which is what we want
    """
    try:
        devices = enumerate_devices(XEnumerationFlags.XEF_EnableAll)
        for d in devices:
            try:
                ser = int(d.serial)
            except (TypeError, ValueError):
                ser = 0
            # Virtual camera has serial 0
            if ser != 0:
                return d.url
        if devices:
            return devices[0].url
    except Exception:
        pass
    return "cam://0"


class xCam:
    def __init__(self, url=None):
        self.cam = XCamera()
        self.init_log: list[str] = []   # captured init diagnostics for the GUI

        # If no URL given, OR the caller passed the broken default
        # cam://0?fg=none, pick a real (non-Virtual) device.
        if not url or "fg=none" in str(url) or url == "cam://0":
            real = pick_real_camera_url()
            if real != url:
                self.init_log.append(f"Camera URL → {real} (was: {url})")
            url = real

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
            
            # The Bobcat-320-GigE stores its calibration ON the camera
            # ("Calibration data: (Camera memory)" in Xeneth's connection
            # setup). Loading a .xca file from disk overrides that with
            # potentially wrong data — skip it unless explicitly asked
            # for via the XENETH_LOAD_CAL_PATH env var.
            cal_override = os.environ.get("XENETH_LOAD_CAL_PATH")
            if cal_override:
                try:
                    self.cam.load_calibration(cal_override, 2)
                    self.init_log.append(f"Calibration file loaded: {cal_override}")
                except Exception as e:
                    self.init_log.append(f"Calibration load FAILED: {e}")
            else:
                self.init_log.append("Using camera-memory calibration (no file loaded)")

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
                    
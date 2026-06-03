# This works specifically and exclusively for the Orange Bobcat.
# Match Caleb's working driver exactly — only diagnostic logging added.
import os
import sys
from xenics.xeneth import *
from xenics.xeneth.errors import XenethAPIException, XenethException
from xenics.xeneth.xcamera import XCamera


def dev_discovery():
    """Enumerate cameras and prompt for selection if more than one."""
    flags = XEnumerationFlags.XEF_EnableAll
    val = 0
    try:
        devices = enumerate_devices(flags)
        if len(devices) == 0:
            print("No devices found")
            sys.exit()

        states = {XDeviceStates.XDS_Available: "Available",
                  XDeviceStates.XDS_Busy: "Busy",
                  XDeviceStates.XDS_Unreachable: "Unreachable"}

        for idx, dev in enumerate(devices):
            print(f"Device[{idx}] {dev.name} @ {dev.address} ({dev.transport})")
            print(f"PID: {dev.pid}")
            print(f"Serial: {dev.serial}")
            print(f"URL: {dev.url}")
            print(f"State: {states[dev.state]} ({dev.state})\n")

        if idx > 1:
            while True:
                try:
                    val = int(input("Enter desired device number: "))
                    if val <= idx:
                        break
                    print(f"Please enter a number less than or equal to {idx}.")
                except ValueError:
                    print("Invalid input. Please enter a valid integer.")
    except XenethException as e:
        print(f"Error occurred during device discovery: {e.message}")

    return devices[val].url


class xCam:
    def __init__(self, url=None):
        self.cam = XCamera()
        self.init_log: list[str] = []  # diagnostics surfaced to GUI
        if not url:
            url = dev_discovery()

        try:
            print(f"Opening connection to {url}")
            self.cam.open(url)
            if self.cam.is_initialized:
                self.pid = self.cam.get_property_value("_CAM_PID")
                self.ser = self.cam.get_property_value("_CAM_SER")
                self.exposure_time = self.cam.get_property_value("ExposureTime")
                print(
                    f"Controlling camera with PID: 0x{int(self.pid):X}, "
                    f"SER: {self.ser}, ExposureTime: {self.exposure_time}"
                )
                self.init_log.append(
                    f"PID 0x{int(self.pid):X} · SER {self.ser} · "
                    f"exposure {self.exposure_time:.0f} µs"
                )

            # Load calibration the way Caleb's working code does
            cal_path = (
                r"C:\Program Files\Xeneth\Calibrations"
                "\\XC-(10-06-2021)-500us_14931.xca"
            )
            local_cal = os.path.join(
                os.path.dirname(__file__),
                "calibration",
                "XC-(10-06-2021)-500us_14931.xca",
            )
            if not os.path.exists(cal_path) and os.path.exists(local_cal):
                cal_path = local_cal
            try:
                self.cam.load_calibration(cal_path, 2)
                self.init_log.append(f"Calibration loaded: {cal_path}")
            except Exception as e:
                self.init_log.append(f"Calibration load failed: {e}")

            self.buffer = self.cam.create_buffer()
            if self.cam.is_initialized:
                print("Start capturing")
                self.cam.start_capture()
            else:
                print("Initialization failed")
        except XenethAPIException as e:
            print(e.message)
            self.init_log.append(f"Open failed: {e.message}")

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

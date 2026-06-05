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
    def __init__(self, url=None, exposure=None):
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

                # Fail fast on a stalled stream. The SDK default
                # (_API_GETFRAME_TIMEOUT) is 10 000 ms, so every blocked
                # grab hangs 10 s — which is what made "no frames" look
                # like a total mystery instead of an obvious error.
                try:
                    self.cam.set_property_value("_API_GETFRAME_TIMEOUT", 1500)
                except Exception:
                    pass

                # Apply the configured exposure. The camera ignores config
                # otherwise and just runs at its calibration default (500 µs).
                if exposure is not None:
                    try:
                        actual = self.setExposure(exposure)
                        self.init_log.append(f"Exposure set to {actual:.0f} µs")
                    except Exception as e:
                        self.init_log.append(f"Exposure set failed: {e}")

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
                # Confirm frames actually arrive. "Connected but no frames"
                # is almost never a light/exposure problem — dark frames
                # still stream. It is almost always one of:
                #   1. Windows Firewall dropping inbound GigE stream (GVSP)
                #      UDP for THIS python.exe. Xeneth64.exe is whitelisted
                #      but the venv python is a different exe and is not.
                #      Fix: run tools/setup_lab_machine.ps1 as admin.
                #   2. Xeneth is open and holding the single stream channel.
                #      Fix: close Xeneth completely.
                if self._probe_frame():
                    print("Streaming OK — frames arriving.")
                    self.init_log.append("Streaming OK — frames arriving.")
                else:
                    msg = ("CONNECTED BUT NO FRAMES — inbound GigE stream is "
                           "being dropped. Most likely Windows Firewall is "
                           "blocking this Python (fix: run "
                           "tools/setup_lab_machine.ps1 as admin), or Xeneth "
                           "is open and holding the camera (close it). This "
                           "is NOT a light/exposure issue.")
                    print(msg)
                    self.init_log.append(msg)
            else:
                print("Initialization failed")
                self.init_log.append("Camera reported not initialized after open.")
        except XenethAPIException as e:
            print(e.message)
            self.init_log.append(f"Open failed: {e.message}")

        self._closed = False

    def _probe_frame(self, attempts=2):
        """Return True if at least one frame arrives. Used at connect to tell
        'stream is dead' (firewall / Xeneth busy) apart from 'just dark'."""
        for _ in range(attempts):
            try:
                if self.cam.get_frame(self.buffer,
                                      flags=XGetFrameFlags.XGF_Blocking):
                    return True
            except Exception:
                pass
        return False

    def setExposure(self, microseconds):
        """Set integration time in µs (Bobcat 320 range ~0.1–262143).
        Returns the value the camera reports back. Safe to call live."""
        us = max(0.1, min(262143.0, float(microseconds)))
        self.cam.set_property_value("ExposureTime", us)
        self.exposure_time = self.cam.get_property_value("ExposureTime")
        return self.exposure_time

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

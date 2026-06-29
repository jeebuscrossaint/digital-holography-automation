# -*- coding: utf-8 -*-
"""Hardware connect / disconnect. Each device connects on its own thread (so a
slow or failing one doesn't block the others), with diagnostics surfaced to the
Activity log on failure."""

import threading
import time

from .diagnostics import friendly_error


class ConnectionMixin:
    def _connect_hardware(self):
        self._connect_btn.setEnabled(False)
        self._log("Connecting to hardware…", "INFO")
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        ok: list[str] = []
        fail: list[str] = []
        lock = threading.Lock()

        def record_ok(name):
            with lock: ok.append(name)
        def record_fail(name):
            with lock: fail.append(name)

        threads = [
            threading.Thread(target=self._connect_laser,  args=(record_ok, record_fail), daemon=True),
            threading.Thread(target=self._connect_camera, args=(record_ok, record_fail), daemon=True),
            threading.Thread(target=self._connect_switch, args=(record_ok, record_fail), daemon=True),
            threading.Thread(target=self._connect_motors, args=(record_ok, record_fail), daemon=True),
        ]
        for t in threads: t.start()
        for t in threads: t.join()

        self._connected_names = ok
        self.hardware_connected = len(ok) > 0
        self._post({"type": "done", "event": "connect", "success": True})

    def _emit(self, text, level="INFO"):
        self._post({"type": "log", "text": text, "level": level})

    def _hw(self, device, status):
        self._post({"type": "hw_status", "device": device, "status": status})

    def _connect_laser(self, record_ok, record_fail):
        self._hw("laser", "connecting")
        cfg_l = self.config.get("hardware", {}).get("laser", {})
        addr  = cfg_l.get("gpib_address", "GPIB0::24::INSTR")
        self._emit(f"Laser — trying {addr}…")
        try:
            from HPTunableLaserSource import HPTunableLaserSource
            self.laser = HPTunableLaserSource(addr)
            # Only set the display unit so queries come back in µW. Don't touch
            # power or output state — keep whatever the laser is set to.
            self.laser.changePowerUnit(cfg_l.get("power_unit", "UW"))
            self._hw("laser", "connected")
            self._emit(f"✓ Laser  {addr}", "OK")
            record_ok("Laser")
        except Exception as e:
            self._hw("laser", "error")
            self._emit(f"✗ Laser — {friendly_error(e)}", "WARN")
            self._emit(f"  raw: {type(e).__name__}: {str(e).splitlines()[0][:200]}", "DEBUG")
            try:
                from HPTunableLaserSource import _make_resource_manager
                res = _make_resource_manager().list_resources()
                if res:
                    self._emit(f"  Visible VISA resources: {', '.join(res)}", "INFO")
                else:
                    self._emit("  No VISA resources visible — adapter driver isn't loaded "
                               "(install NI-488.2 or Keysight IO Libraries)", "WARN")
            except Exception as e2:
                self._emit(f"  VISA enumeration failed: {type(e2).__name__}: {e2}", "DEBUG")
            record_fail("Laser")

    def _connect_camera(self, record_ok, record_fail):
        self._hw("camera", "connecting")
        cfg_c = self.config.get("hardware", {}).get("camera", {})
        url   = cfg_c.get("url", "cam://0")
        if not url or url in ("auto", ""):
            url = "cam://0"
        self._emit(f"Camera — trying {url}…")
        try:
            from XenicsCam import xCam
            exposure = cfg_c.get("exposure_time", None)
            self.camera = xCam(url=url, exposure=exposure)
            ser = int(self.camera.ser) if self.camera.ser else "?"
            self._hw("camera", "connected")
            self._emit(f"✓ Camera  Xenics Bobcat 320 GigE  SER:{ser}", "OK")
            no_frames = False
            for line in getattr(self.camera, "init_log", []):
                # Escalate the self-diagnostics so a dead stream is obvious.
                # "Connected but no frames" is the trap that cost days.
                if "NO FRAMES" in line:
                    no_frames = True
                    self._emit(f"  ⚠ {line}", "WARN")
                elif line.startswith("Streaming OK"):
                    self._emit(f"  {line}", "OK")
                else:
                    self._emit(f"  {line}", "DEBUG")
            if no_frames:
                self._hw("camera", "error")
            record_ok("Camera")
        except Exception as e:
            self._hw("camera", "error")
            self._emit(f"✗ Camera — {friendly_error(e)}", "WARN")
            record_fail("Camera")

    def _connect_switch(self, record_ok, record_fail):
        self._hw("switch", "connecting")
        cfg_s = self.config.get("hardware", {}).get("fiber_switch", {})
        port  = cfg_s.get("port", "COM6")
        self._emit(f"Fiber switch — trying {port}…")
        try:
            from D700DiconSwitch import D700DiconSwitch
            self.switch = D700DiconSwitch(port=port, baudrate=cfg_s.get("baudrate", 9600))
            actual_port = getattr(self.switch, "port", port)
            self._hw("switch", "connected")
            if actual_port != port:
                self._emit(f"  (auto-detected switch on {actual_port}, not "
                           f"configured {port})", "INFO")
            self._emit(f"✓ Switch  Dicon GP700  {actual_port}", "OK")
            # Confirm the device actually talks back (opening proves nothing).
            try:
                ident = self.switch.identify() if hasattr(self.switch, "identify") else ""
                if ident:
                    self._emit(f"  Switch ID: {ident}", "OK")
                else:
                    self._emit("  ⚠ Switch gave no ID — port opened but the "
                               "device isn't answering (check power/baud). Leg "
                               "commands are sent open-loop and can't be verified.",
                               "WARN")
            except Exception as e:
                self._emit(f"  Switch ID query failed: {e}", "DEBUG")
            record_ok("Switch")
        except Exception as e:
            self._hw("switch", "error")
            self._emit(f"✗ Switch — {friendly_error(e)}", "WARN")
            try:
                from serial.tools import list_ports
                ports = list(list_ports.comports())
                if ports:
                    self._emit("  Available COM ports:", "INFO")
                    for p in ports:
                        desc = (p.description or "").strip()
                        self._emit(f"    {p.device}  ({desc})", "INFO")
                    self._emit(
                        "  Switch should appear as something like 'USB Serial Port' "
                        "or 'Prolific / FTDI USB-to-Serial'. Set 'fiber_switch.port' in "
                        "Configuration to the matching one.", "INFO")
                else:
                    self._emit("  No COM ports visible — switch isn't plugged in, "
                               "or the USB-to-serial driver isn't installed.", "WARN")
            except Exception as e2:
                self._emit(f"  Couldn't enumerate COM ports: {e2}", "DEBUG")
            record_fail("Switch")

    def _connect_motors(self, record_ok, record_fail):
        self._hw("motors", "connecting")
        cfg_m  = self.config.get("hardware", {}).get("polarization_motors", {})
        serial = str(cfg_m.get("serial_number", "38394984"))
        self._emit(f"Polarization motors — SN {serial}…")
        try:
            from polMotors import polMotors
            self.motors = polMotors(serialNumber=serial.encode())
            # Don't auto-home or auto-move — that puts paddle 3 in a state where
            # subsequent moves are ignored on this firmware.
            self._hw("motors", "connected")
            self._emit(f"✓ Motors  Thorlabs MPC320  SN:{serial}  connected", "OK")
            for p in (1, 2, 3):
                try:
                    pos = self.motors.getPosition(p)
                    bits = self.motors._status(p) if hasattr(self.motors, "_status") else 0
                    self._emit(f"  Paddle {p}: pos={pos:.2f}°  status=0x{bits:08x}", "DEBUG")
                except Exception as e:
                    self._emit(f"  Paddle {p}: state read failed — {e}", "WARN")
            record_ok("Motors")
        except Exception as e:
            self._hw("motors", "error")
            self._emit(f"✗ Motors — {friendly_error(e)}", "WARN")
            record_fail("Motors")

    def _shutdown_hardware(self):
        """Safely power down + close every connected instrument. Best-effort:
        each step independent so one failure doesn't strand the others."""
        for obj, method in [
            (self.laser,  lambda: (self.laser.outputState(False), self.laser.closeConnection())),
            (self.camera, lambda: (self.camera.stopCapture(), self.camera.closeCamera())),
            (self.switch, lambda: self.switch.close()),
            (self.motors, lambda: self.motors.close()),
        ]:
            if obj:
                try: method()
                except Exception: pass

    def _disconnect_hardware(self):
        if self.experiment_running:
            self._stop_experiment()
            time.sleep(0.5)

        self._log("Disconnecting hardware…", "INFO")
        self._shutdown_hardware()

        self.laser = self.camera = self.switch = self.motors = None
        self.hardware_connected = False

        for dev in self._hw_dots:
            self._set_hw_dot(dev, "disconnected")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._start_btn.setEnabled(True)   # keep Process usable offline
        self._status_lbl.setText("Hardware disconnected")
        self._log("Hardware disconnected", "INFO")

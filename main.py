# -*- coding: utf-8 -*-
"""
UCF CREOL - Photonic Lantern Digital Holography Control
Run with: python main.py
"""

import os
import sys
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from datetime import datetime

# ── Environment setup (must happen before any hardware imports) ──────────────

SCRIPT_DIR = Path(__file__).parent

# Add Xeneth DLL to Windows DLL search path
_XENETH_RUNTIME = r"C:\Program Files\Common Files\XenICs\Runtime"
if os.path.exists(_XENETH_RUNTIME):
    try:
        os.add_dll_directory(_XENETH_RUNTIME)
    except AttributeError:
        pass  # Python < 3.8
    os.environ["PATH"] = _XENETH_RUNTIME + os.pathsep + os.environ.get("PATH", "")

# Hardware driver paths (hardware/) and processing libs (lib/)
for p in (str(SCRIPT_DIR / "hardware"), str(SCRIPT_DIR / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

CONFIG_FILE = str(SCRIPT_DIR / "experiment_config.yaml")

# ── Theme (Catppuccin Mocha) ─────────────────────────────────────────────────
BG      = "#1e1e2e"
PANEL   = "#313244"
FG      = "#cdd6f4"
GREEN   = "#a6e3a1"
RED     = "#f38ba8"
YELLOW  = "#f9e2af"
BLUE    = "#89b4fa"
MAUVE   = "#cba6f7"
SURFACE = "#45475a"

HW_STATUS_COLOR = {
    "connected":    GREEN,
    "disconnected": RED,
    "connecting":   YELLOW,
    "error":        RED,
}

LOG_TAG_COLOR = {
    "INFO":  FG,
    "OK":    GREEN,
    "WARN":  YELLOW,
    "ERROR": RED,
    "DEBUG": "#6c7086",
}


# ── Application ───────────────────────────────────────────────────────────────

class HolographyApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("UCF CREOL | Photonic Lantern Holography Control")
        self.root.geometry("1300x880")
        self.root.configure(bg=BG)

        self.hardware_connected = False
        self.experiment_running = False
        self.stop_event = threading.Event()
        self.msg_queue: queue.Queue = queue.Queue()

        self.laser  = None
        self.camera = None
        self.switch = None
        self.motors = None
        self.config = self._load_config()

        self._setup_styles()
        self._build_ui()
        self._poll_queue()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            import yaml
            with open(CONFIG_FILE) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    # ── Styles ────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".",            background=BG,    foreground=FG,  font=("Helvetica", 10))
        s.configure("TFrame",       background=BG)
        s.configure("TLabel",       background=BG,    foreground=FG)
        s.configure("TButton",      background=SURFACE, foreground=FG, borderwidth=0, padding=6)
        s.map("TButton",            background=[("active", BLUE), ("disabled", SURFACE)],
                                    foreground=[("active", BG), ("disabled", "#6c7086")])
        s.configure("Accent.TButton", background=BLUE, foreground=BG)
        s.map("Accent.TButton",     background=[("active", MAUVE)])
        s.configure("Stop.TButton", background=RED,  foreground=BG)
        s.map("Stop.TButton",       background=[("active", "#eba0ac")])
        s.configure("TNotebook",    background=BG, tabmargins=[2, 5, 2, 0])
        s.configure("TNotebook.Tab", background=PANEL, foreground=FG, padding=[12, 5])
        s.map("TNotebook.Tab",       background=[("selected", BLUE)],
                                     foreground=[("selected", BG)])
        s.configure("TProgressbar", troughcolor=PANEL, background=GREEN, thickness=18)
        s.configure("TEntry",        fieldbackground=PANEL, foreground=FG, insertcolor=FG)
        s.configure("TRadiobutton",  background=BG,    foreground=FG)
        s.configure("Panel.TFrame",  background=PANEL)
        s.configure("Panel.TLabel",  background=PANEL, foreground=FG)
        s.configure("Treeview",      background=PANEL, foreground=FG,
                                     fieldbackground=PANEL, rowheight=22)
        s.configure("Treeview.Heading", background=SURFACE, foreground=FG,
                                        font=("Helvetica", 10, "bold"))
        s.map("Treeview",            background=[("selected", BLUE)])
        s.configure("TSeparator",    background=SURFACE)
        s.configure("TScrollbar",    background=SURFACE, troughcolor=PANEL)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        title_row = ttk.Frame(self.root)
        title_row.pack(fill="x", padx=14, pady=(10, 4))
        ttk.Label(title_row,
                  text="UCF CREOL — Photonic Lantern Digital Holography",
                  font=("Helvetica", 15, "bold"), foreground=BLUE).pack(side="left")
        ttk.Label(title_row, text="python main.py",
                  font=("Consolas", 9), foreground="#6c7086").pack(side="right")

        self._build_hw_bar()

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=14, pady=6)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(side="left", fill="both", expand=True)

        self._build_run_tab()
        self._build_config_tab()
        self._build_results_tab()

        self._build_log_panel(main)

    # ── Hardware bar ──────────────────────────────────────────────────────────

    def _build_hw_bar(self):
        bar = tk.Frame(self.root, bg=PANEL, pady=6)
        bar.pack(fill="x", padx=14, pady=(0, 4))

        tk.Label(bar, text="Hardware:", bg=PANEL, fg=FG,
                 font=("Helvetica", 10, "bold")).pack(side="left", padx=12)

        self._hw_dots: dict = {}
        for name in ("Laser", "Camera", "Switch", "Motors"):
            f = tk.Frame(bar, bg=PANEL)
            f.pack(side="left", padx=16)
            dot = tk.Label(f, text="●", bg=PANEL, fg=RED, font=("Helvetica", 14))
            dot.pack(side="left")
            tk.Label(f, text=f" {name}", bg=PANEL, fg=FG).pack(side="left")
            self._hw_dots[name.lower()] = dot

        btn_row = tk.Frame(bar, bg=PANEL)
        btn_row.pack(side="right", padx=12)

        self._connect_btn = ttk.Button(btn_row, text="Connect All",
                                       style="Accent.TButton",
                                       command=self._connect_hardware)
        self._connect_btn.pack(side="left", padx=4)

        self._disconnect_btn = ttk.Button(btn_row, text="Disconnect",
                                          command=self._disconnect_hardware,
                                          state="disabled")
        self._disconnect_btn.pack(side="left", padx=4)

    # ── Run tab ───────────────────────────────────────────────────────────────

    def _build_run_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Run Experiment  ")

        # Mode + controls
        ctrl = tk.Frame(tab, bg=PANEL, pady=8)
        ctrl.pack(fill="x", padx=6, pady=(6, 3))

        tk.Label(ctrl, text="Mode:", bg=PANEL, fg=FG).pack(side="left", padx=(12, 6))
        self._run_mode = tk.StringVar(value="full")
        for label, val in (("Collect", "collect"), ("Process", "process"), ("Full Run", "full")):
            tk.Radiobutton(ctrl, text=label, variable=self._run_mode, value=val,
                           bg=PANEL, fg=FG, selectcolor=SURFACE,
                           activebackground=PANEL, activeforeground=FG).pack(side="left", padx=8)

        self._stop_btn = ttk.Button(ctrl, text="■  STOP",
                                    style="Stop.TButton",
                                    command=self._stop_experiment,
                                    state="disabled")
        self._stop_btn.pack(side="right", padx=(6, 12))

        self._start_btn = ttk.Button(ctrl, text="▶  START",
                                     style="Accent.TButton",
                                     command=self._start_experiment,
                                     state="disabled")
        self._start_btn.pack(side="right", padx=4)

        # Progress
        prog = tk.Frame(tab, bg=PANEL, pady=6)
        prog.pack(fill="x", padx=6, pady=3)

        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(prog, variable=self._progress_var,
                         maximum=100).pack(fill="x", padx=12, pady=(4, 2))

        self._status_var = tk.StringVar(value="Connect hardware to begin")
        tk.Label(prog, textvariable=self._status_var,
                 bg=PANEL, fg=FG, font=("Helvetica", 10)).pack(anchor="w", padx=12)

        detail = tk.Frame(prog, bg=PANEL)
        detail.pack(fill="x", padx=12, pady=(3, 6))
        self._leg_var    = tk.StringVar(value="Leg: —")
        self._wl_var     = tk.StringVar(value="λ: —")
        self._acq_var    = tk.StringVar(value="Images: 0/0")
        self._fringe_var = tk.StringVar(value="Fringe: —")
        for v in (self._leg_var, self._wl_var, self._acq_var, self._fringe_var):
            tk.Label(detail, textvariable=v, bg=PANEL, fg="#a6adc8",
                     font=("Helvetica", 9)).pack(side="left", padx=14)

        # Camera preview
        preview = ttk.Frame(tab)
        preview.pack(fill="both", expand=True, padx=6, pady=6)
        ttk.Label(preview, text="Camera Preview",
                  font=("Helvetica", 10, "bold")).pack(anchor="w", padx=4)

        self._canvas = tk.Canvas(preview, bg="black", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas_photo = None
        self._last_frame   = None
        self._canvas.bind("<Configure>", lambda _e: self._redraw_frame())
        self._canvas.create_text(200, 120, text="No Signal",
                                  fill="#6c7086", font=("Helvetica", 14),
                                  tags="nosignal")

    # ── Config tab ────────────────────────────────────────────────────────────

    def _build_config_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Configuration  ")

        outer = tk.Canvas(tab, bg=BG, highlightthickness=0)
        vsb   = ttk.Scrollbar(tab, orient="vertical", command=outer.yview)
        outer.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        outer.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(outer)
        inner.bind("<Configure>",
                   lambda e: outer.configure(scrollregion=outer.bbox("all")))
        outer.create_window((0, 0), window=inner, anchor="nw")

        self._cfg_vars: dict = {}

        def section(title: str):
            ttk.Label(inner, text=title, font=("Helvetica", 11, "bold"),
                      foreground=BLUE).pack(anchor="w", padx=14, pady=(12, 2))

        def field(label: str, key: str, default):
            row = ttk.Frame(inner)
            row.pack(fill="x", padx=14, pady=2)
            ttk.Label(row, text=label, width=34, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(default))
            ttk.Entry(row, textvariable=var, width=44).pack(side="left", padx=6)
            self._cfg_vars[key] = var

        hw  = self.config.get("hardware", {})
        exp = self.config.get("experiment", {})

        section("Hardware")
        field("Laser GPIB Address",       "hardware.laser.gpib_address",
              hw.get("laser", {}).get("gpib_address", "GPIB0::24::INSTR"))
        field("Laser Power (µW)",          "hardware.laser.power_uw",
              hw.get("laser", {}).get("power_uw", 208))
        field("Camera URL",                "hardware.camera.url",
              hw.get("camera", {}).get("url", "cam://0"))
        field("Camera Exposure (µs)",      "hardware.camera.exposure_time",
              hw.get("camera", {}).get("exposure_time", 500))
        field("Fiber Switch COM Port",     "hardware.fiber_switch.port",
              hw.get("fiber_switch", {}).get("port", "COM6"))
        field("Motor Serial Number",       "hardware.polarization_motors.serial_number",
              hw.get("polarization_motors", {}).get("serial_number", "38394984"))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)
        section("Experiment")
        legs = exp.get("legs", list(range(1, 8)))
        field("Legs (comma-separated)",       "experiment.legs",
              ",".join(map(str, legs)))
        wls = exp.get("wavelengths", [1540, 1545, 1550, 1555, 1560, 1565, 1570])
        field("Wavelengths nm (comma-sep)",   "experiment.wavelengths",
              ",".join(map(str, wls)))
        wt = exp.get("wait_times", {})
        field("Wait after leg switch (s)",    "experiment.wait_times.after_leg_switch",
              wt.get("after_leg_switch", 1.0))
        field("Wait after wavelength (s)",    "experiment.wait_times.after_wavelength_change",
              wt.get("after_wavelength_change", 0.5))
        fd = exp.get("fringe_detection", {})
        field("Min fringe visibility",        "experiment.fringe_detection.min_visibility",
              fd.get("min_visibility", 0.15))
        field("Max polarization attempts",    "experiment.fringe_detection.max_attempts",
              fd.get("max_attempts", 5))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=14, pady=6)
        section("Output")
        field("Data output directory",        "data.output_dir",
              self.config.get("data", {}).get("output_dir", "./holography_data"))

        ttk.Button(inner, text="Save Configuration",
                   command=self._save_config).pack(padx=14, pady=12, anchor="w")

    # ── Results tab ───────────────────────────────────────────────────────────

    def _build_results_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Results  ")

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill="x", padx=10, pady=6)
        ttk.Button(btn_row, text="Open Data Folder",
                   command=self._open_data_folder).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Refresh",
                   command=self._refresh_results).pack(side="left", padx=4)

        cols = ("file", "fidelity", "mode_powers")
        self._results_tree = ttk.Treeview(tab, columns=cols, show="headings", height=24)
        self._results_tree.heading("file",        text="Hologram File")
        self._results_tree.heading("fidelity",    text="Fidelity")
        self._results_tree.heading("mode_powers", text="Mode Powers (LP01 → LP06)")
        self._results_tree.column("file",        width=220)
        self._results_tree.column("fidelity",    width=80)
        self._results_tree.column("mode_powers", width=380)

        vsb = ttk.Scrollbar(tab, orient="vertical", command=self._results_tree.yview)
        self._results_tree.configure(yscrollcommand=vsb.set)
        self._results_tree.pack(side="left", fill="both", expand=True,
                                padx=(10, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 10))

    # ── Log panel ─────────────────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        pane = ttk.Frame(parent)
        pane.pack(side="right", fill="both", padx=(8, 0))

        hdr = ttk.Frame(pane)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="Log", font=("Helvetica", 10, "bold")).pack(side="left", padx=4)
        ttk.Button(hdr, text="Clear", command=self._clear_log).pack(side="right")

        self._log_widget = scrolledtext.ScrolledText(
            pane, width=46, bg="#11111b", fg=FG,
            font=("Consolas", 9), state="disabled", wrap="word",
            insertbackground=FG,
        )
        self._log_widget.pack(fill="both", expand=True)

        for tag, color in LOG_TAG_COLOR.items():
            self._log_widget.tag_config(tag, foreground=color)

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, text: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.configure(state="normal")
        self._log_widget.insert("end", f"[{ts}] {text}\n", level)
        self._log_widget.see("end")
        self._log_widget.configure(state="disabled")

    def _clear_log(self):
        self._log_widget.configure(state="normal")
        self._log_widget.delete("1.0", "end")
        self._log_widget.configure(state="disabled")

    # ── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                t = msg.get("type")
                if t == "log":
                    self._log(msg["text"], msg.get("level", "INFO"))
                elif t == "hw_status":
                    self._set_hw_dot(msg["device"], msg["status"])
                elif t == "progress":
                    self._update_progress(msg)
                elif t == "frame":
                    self._show_frame(msg["data"])
                elif t == "done":
                    self._on_done(msg.get("event"), msg.get("success", True))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ── Hardware dots ─────────────────────────────────────────────────────────

    def _set_hw_dot(self, device: str, status: str):
        dot = self._hw_dots.get(device)
        if dot:
            dot.configure(fg=HW_STATUS_COLOR.get(status, RED))

    # ── Progress updates ──────────────────────────────────────────────────────

    def _update_progress(self, msg: dict):
        if "percent"    in msg: self._progress_var.set(msg["percent"])
        if "status"     in msg: self._status_var.set(msg["status"])
        if "leg"        in msg and "total_legs" in msg:
            self._leg_var.set(f"Leg: {msg['leg']}/{msg['total_legs']}")
        if "wavelength" in msg: self._wl_var.set(f"λ: {msg['wavelength']} nm")
        if "acq"        in msg and "total_acq" in msg:
            self._acq_var.set(f"Images: {msg['acq']}/{msg['total_acq']}")
        if "fringe_metric" in msg:
            self._fringe_var.set(f"Fringe: {msg['fringe_metric']:.3f}")

    # ── Camera preview ────────────────────────────────────────────────────────

    def _redraw_frame(self):
        if self._last_frame is not None:
            self._show_frame(self._last_frame)

    def _show_frame(self, data):
        self._last_frame = data
        try:
            from PIL import Image, ImageTk
            import numpy as np

            arr = np.asarray(data, dtype=float)
            mn, mx = arr.min(), arr.max()
            if mx > mn:
                arr = (arr - mn) / (mx - mn) * 255
            arr = arr.astype(np.uint8)

            cw = max(self._canvas.winfo_width(),  10)
            ch = max(self._canvas.winfo_height(), 10)

            img   = Image.fromarray(arr, mode="L").resize((cw, ch), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._canvas.delete("nosignal")
            self._canvas.create_image(0, 0, anchor="nw", image=photo)
            self._canvas_photo = photo  # prevent GC
        except Exception:
            pass

    # ── Connect / disconnect ──────────────────────────────────────────────────

    def _connect_hardware(self):
        self._connect_btn.configure(state="disabled")
        self._log("Connecting to hardware…", "INFO")
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        q = self.msg_queue

        def emit(text, level="INFO"):
            q.put({"type": "log", "text": text, "level": level})

        def hw(device, status):
            q.put({"type": "hw_status", "device": device, "status": status})

        # Laser ---------------------------------------------------------------
        hw("laser", "connecting")
        emit("Connecting to HP Tunable Laser…")
        try:
            from HPTunableLaserSource import HPTunableLaserSource
            cfg_l = self.config.get("hardware", {}).get("laser", {})
            self.laser = HPTunableLaserSource(
                cfg_l.get("gpib_address", "GPIB0::24::INSTR"))
            self.laser.changePowerUnit(cfg_l.get("power_unit", "UW"))
            self.laser.powerAmplitude(cfg_l.get("power_uw", 208))
            self.laser.outputState(True)
            hw("laser", "connected")
            emit("✓ Laser connected and output ON", "OK")
        except Exception as e:
            hw("laser", "error")
            emit(f"✗ Laser: {e}", "WARN")

        # Camera --------------------------------------------------------------
        hw("camera", "connecting")
        emit("Connecting to Xenics Bobcat camera…")
        try:
            from XenicsCam import xCam, dev_discovery
            cfg_c = self.config.get("hardware", {}).get("camera", {})
            url = cfg_c.get("url", "cam://0")
            if not url or url in ("auto", ""):
                url = dev_discovery()
            self.camera = xCam(url=url)
            hw("camera", "connected")
            emit(f"✓ Camera connected (SER:{int(self.camera.ser)})", "OK")
            frame = self.camera.getFrame()
            if frame is not None:
                q.put({"type": "frame", "data": frame})
        except Exception as e:
            hw("camera", "error")
            emit(f"✗ Camera: {e}", "WARN")

        # Fiber switch --------------------------------------------------------
        hw("switch", "connecting")
        emit("Connecting to Dicon fiber switch…")
        try:
            from D700DiconSwitch import D700DiconSwitch
            cfg_s = self.config.get("hardware", {}).get("fiber_switch", {})
            self.switch = D700DiconSwitch(
                port=cfg_s.get("port", "COM6"),
                baudrate=cfg_s.get("baudrate", 9600))
            hw("switch", "connected")
            emit(f"✓ Switch connected ({cfg_s.get('port', 'COM6')})", "OK")
        except Exception as e:
            hw("switch", "error")
            emit(f"✗ Switch: {e}", "WARN")

        # Polarization motors -------------------------------------------------
        hw("motors", "connecting")
        emit("Connecting to Thorlabs polarization motors…")
        try:
            from polMotors import polMotors
            cfg_m = self.config.get("hardware", {}).get("polarization_motors", {})
            serial = str(cfg_m.get("serial_number", "38394984")).encode()
            self.motors = polMotors(serialNumber=serial)
            for i, angle in enumerate(cfg_m.get("initial_angles", [0, 0, 0])):
                self.motors.moveMotor(i + 1, angle)
            while self.motors.isBusy():
                time.sleep(0.1)
            hw("motors", "connected")
            emit("✓ Motors connected and homed", "OK")
        except Exception as e:
            hw("motors", "error")
            emit(f"✗ Motors: {e}", "WARN")

        self.hardware_connected = True
        q.put({"type": "done", "event": "connect", "success": True})

    def _disconnect_hardware(self):
        if self.experiment_running:
            self._stop_experiment()
            time.sleep(0.5)

        self._log("Disconnecting hardware…", "INFO")
        for obj, method in [
            (self.laser,  lambda: self.laser.outputState(False)),
            (self.camera, lambda: (self.camera.stopCapture(), self.camera.closeCamera())),
            (self.switch, lambda: self.switch.close()),
        ]:
            if obj:
                try: method()
                except Exception: pass

        self.laser = self.camera = self.switch = self.motors = None
        self.hardware_connected = False

        for dev in self._hw_dots:
            self._set_hw_dot(dev, "disconnected")
        self._connect_btn.configure(state="normal")
        self._disconnect_btn.configure(state="disabled")
        self._start_btn.configure(state="disabled")
        self._status_var.set("Hardware disconnected")
        self._log("Hardware disconnected", "INFO")

    # ── Experiment ────────────────────────────────────────────────────────────

    def _start_experiment(self):
        if not self.hardware_connected:
            messagebox.showwarning("Not Connected", "Connect hardware first.")
            return
        mode = self._run_mode.get()
        self.experiment_running = True
        self.stop_event.clear()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._status_var.set("Starting…")
        self._log(f"Experiment started (mode: {mode})", "INFO")
        threading.Thread(target=self._experiment_worker,
                         args=(mode,), daemon=True).start()

    def _stop_experiment(self):
        self.stop_event.set()
        self._stop_btn.configure(state="disabled")
        self._log("Stop requested — finishing current acquisition…", "WARN")

    def _experiment_worker(self, mode: str):
        q = self.msg_queue
        cb = q.put

        try:
            if mode in ("collect", "full"):
                self._run_collection(cb)
            if mode in ("process", "full") and not self.stop_event.is_set():
                self._run_processing(cb)

            if self.stop_event.is_set():
                cb({"type": "log", "text": "Experiment stopped by user.", "level": "WARN"})
                q.put({"type": "done", "event": "experiment", "success": False})
            else:
                cb({"type": "log", "text": "✓ Experiment complete!", "level": "OK"})
                q.put({"type": "done", "event": "experiment", "success": True})
        except Exception as e:
            import traceback
            cb({"type": "log", "text": f"Experiment error: {e}", "level": "ERROR"})
            cb({"type": "log", "text": traceback.format_exc(), "level": "DEBUG"})
            q.put({"type": "done", "event": "experiment", "success": False})

    # ── Collection ────────────────────────────────────────────────────────────

    def _run_collection(self, cb):
        import numpy as np
        import yaml
        from fringe_detection import (check_fringes_visible,
                                       optimize_polarization_for_fringes)

        cfg    = self.config
        legs   = cfg["experiment"]["legs"]
        wls    = cfg["experiment"]["wavelengths"]
        waits  = cfg["experiment"]["wait_times"]
        fdet   = cfg["experiment"]["fringe_detection"]
        fmt    = cfg["data"]["filename_format"]
        out    = Path(cfg["data"]["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        module = cfg["hardware"]["fiber_switch"]["module"]
        total  = len(legs) * len(wls)
        n      = 0

        cb({"type": "log",
            "text": f"Collection: {len(legs)} legs × {len(wls)} wavelengths = {total} images",
            "level": "INFO"})

        for li, leg in enumerate(legs):
            if self.stop_event.is_set():
                break

            cb({"type": "log", "text": f"── Leg {leg} ──", "level": "INFO"})
            cb({"type": "progress", "leg": li + 1, "total_legs": len(legs),
                "status": f"Switching to leg {leg}…"})

            if self.switch:
                self.switch.move_to_position(module, leg)
            time.sleep(waits["after_leg_switch"])

            for _wi, wl in enumerate(wls):
                if self.stop_event.is_set():
                    break

                n += 1
                cb({"type": "progress",
                    "percent": (n - 1) / total * 100,
                    "leg": li + 1, "total_legs": len(legs),
                    "wavelength": wl,
                    "acq": n, "total_acq": total,
                    "status": f"Leg {leg}, λ={wl} nm — setting wavelength…"})

                if self.laser:
                    self.laser.changeWavelength(wl)
                time.sleep(waits["after_wavelength_change"])

                frame = self.camera.getFrame() if self.camera else None

                if frame is not None:
                    cb({"type": "frame", "data": frame})

                    if fdet["enabled"]:
                        method    = fdet["check_method"]
                        threshold = fdet["min_visibility"]
                        ok, metric = check_fringes_visible(frame, method, threshold)
                        cb({"type": "progress", "fringe_metric": metric,
                            "status": f"Leg {leg}, λ={wl} nm — fringe: {metric:.3f}"})

                        if not ok and self.motors:
                            cb({"type": "log",
                                "text": f"  Low fringes ({metric:.3f}) — optimizing polarization…",
                                "level": "WARN"})
                            success, best, _ = optimize_polarization_for_fringes(
                                self.camera, self.motors,
                                max_attempts=fdet["max_attempts"],
                                method=method, threshold=threshold)
                            if success:
                                cb({"type": "log",
                                    "text": f"  ✓ Polarization optimized (metric={best:.3f})",
                                    "level": "OK"})
                                time.sleep(waits["after_polarization_adjust"])
                                frame = self.camera.getFrame()
                                if frame is not None:
                                    cb({"type": "frame", "data": frame})
                            else:
                                cb({"type": "log",
                                    "text": f"  ⚠ Could not optimize (best={best:.3f}) — saving anyway",
                                    "level": "WARN"})
                        elif ok:
                            cb({"type": "log",
                                "text": f"  ✓ Fringes OK ({metric:.3f})", "level": "OK"})
                else:
                    cb({"type": "log",
                        "text": "  ✗ Frame capture failed — skipping", "level": "WARN"})

                if frame is not None:
                    fname = fmt.format(leg=leg, wavelength=wl)
                    fpath = out / fname
                    np.save(fpath, frame)

                    if cfg["data"]["save_metadata"]:
                        try:
                            angles = list(self.motors.angles)
                        except Exception:
                            angles = [0, 0, 0]
                        meta = {"leg": leg, "wavelength_nm": wl,
                                "timestamp": datetime.now().isoformat(),
                                "motor_angles": angles}
                        with open(fpath.with_suffix(".yaml"), "w") as f:
                            yaml.dump(meta, f)

                    cb({"type": "log", "text": f"  💾 {fname}", "level": "OK"})

                cb({"type": "progress",
                    "percent": n / total * 100,
                    "acq": n, "total_acq": total,
                    "status": f"Completed {n}/{total} images"})

        cb({"type": "log",
            "text": f"Collection done — {n} images saved to {out}", "level": "OK"})

    # ── Processing ────────────────────────────────────────────────────────────

    def _run_processing(self, cb):
        import yaml

        cb({"type": "log",  "text": "Starting data processing…", "level": "INFO"})
        cb({"type": "progress", "status": "Loading processor…", "percent": 0})

        try:
            from data_processing import HolographyDataProcessor
            proc = HolographyDataProcessor(config_file=CONFIG_FILE)
        except Exception as e:
            cb({"type": "log", "text": f"Processor init failed: {e}", "level": "ERROR"})
            return

        files = sorted(Path(proc.data_dir).glob("leg*.npy"))
        if not files:
            cb({"type": "log",
                "text": "No hologram files found — run collection first", "level": "WARN"})
            return

        cb({"type": "log", "text": f"Found {len(files)} holograms", "level": "INFO"})

        for i, fpath in enumerate(files):
            if self.stop_event.is_set():
                break

            cb({"type": "progress",
                "percent": i / len(files) * 100,
                "status":  f"Processing {fpath.name} ({i+1}/{len(files)})",
                "acq": i + 1, "total_acq": len(files)})
            cb({"type": "log", "text": f"Processing: {fpath.name}", "level": "INFO"})

            try:
                hologram = proc.load_hologram(fpath)
                wl = 1550
                meta_f = fpath.with_suffix(".yaml")
                if meta_f.exists():
                    with open(meta_f) as f:
                        wl = yaml.safe_load(f).get("wavelength_nm", 1550)

                results = proc.process_single_hologram(
                    hologram, wavelength_nm=wl,
                    show_plots=False, save_plots=True,
                    plot_prefix=fpath.stem)
                powers_str = " ".join(
                    f"{p*100:.1f}%" for p in results["mode_powers"][:5])
                cb({"type": "log",
                    "text": f"  ✓ Fidelity: {results['fidelity']:.4f}  [{powers_str}]",
                    "level": "OK"})
            except Exception as e:
                import traceback
                cb({"type": "log", "text": f"  ✗ {e}", "level": "ERROR"})
                cb({"type": "log", "text": traceback.format_exc(), "level": "DEBUG"})

        cb({"type": "progress", "percent": 100, "status": "Processing complete"})
        cb({"type": "log", "text": "Data processing complete", "level": "OK"})

    # ── Done handler ──────────────────────────────────────────────────────────

    def _on_done(self, event: str, success: bool):
        self.experiment_running = False
        self._stop_btn.configure(state="disabled")

        if event == "connect":
            self._connect_btn.configure(state="disabled")
            self._disconnect_btn.configure(state="normal")
            self._start_btn.configure(state="normal")
            self._status_var.set("Hardware connected — ready to run")
            self._log("All hardware connected. Click ▶ START when ready.", "OK")
        elif event == "experiment":
            self._start_btn.configure(
                state="normal" if self.hardware_connected else "disabled")
            if success:
                self._progress_var.set(100)
                self._status_var.set("Experiment complete!")
                self._refresh_results()
                messagebox.showinfo("Done",
                    "Experiment completed successfully!\nCheck the Results tab.")
            else:
                self._status_var.set("Stopped / error — see log")

    # ── Config save ───────────────────────────────────────────────────────────

    def _save_config(self):
        import yaml

        try:
            with open(CONFIG_FILE) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}

        for key_path, var in self._cfg_vars.items():
            raw = var.get().strip()
            if "," in raw:
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                try:
                    val = [int(p) if "." not in p else float(p) for p in parts]
                except ValueError:
                    val = parts
            elif raw.lstrip("-").replace(".", "", 1).isdigit():
                val = float(raw) if "." in raw else int(raw)
            else:
                val = raw

            keys = key_path.split(".")
            d = cfg
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = val

        with open(CONFIG_FILE, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False)

        self.config = self._load_config()
        self._log("Configuration saved", "OK")
        messagebox.showinfo("Saved", "Configuration saved to experiment_config.yaml")

    # ── Results ───────────────────────────────────────────────────────────────

    def _open_data_folder(self):
        import subprocess
        d = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        d.mkdir(exist_ok=True)
        subprocess.Popen(f'explorer "{d.absolute()}"')

    def _refresh_results(self):
        import yaml
        self._results_tree.delete(*self._results_tree.get_children())
        try:
            data_dir     = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
            summary_file = data_dir / "processed_results" / "processing_summary.yaml"
            if not summary_file.exists():
                return
            with open(summary_file) as f:
                summary = yaml.safe_load(f) or {}
            for res in summary.get("results", []):
                powers = res.get("mode_powers", [])
                pstr   = "  ".join(f"{p*100:.1f}%" for p in powers[:6])
                self._results_tree.insert("", "end", values=(
                    res.get("filename", ""),
                    f"{res.get('fidelity', 0):.4f}",
                    pstr,
                ))
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    HolographyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

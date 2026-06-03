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
from tkinter import ttk, scrolledtext, messagebox, font as tkfont
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

# ── Windows 11 Fluent colors (used for status indicators + log) ──────────────
# Theme itself (backgrounds, buttons, tabs, etc.) comes from sv-ttk.

ACCENT_GREEN  = "#16C60C"   # Windows accent: success
ACCENT_AMBER  = "#FFB900"   # Windows accent: caution
ACCENT_RED    = "#E81123"   # Windows accent: danger
ACCENT_BLUE   = "#0078D4"   # Windows accent: info
MUTED         = "#888888"

HW_STATUS_COLOR = {
    "connected":    ACCENT_GREEN,
    "disconnected": MUTED,
    "connecting":   ACCENT_AMBER,
    "error":        ACCENT_RED,
}

HW_STATUS_TEXT = {
    "connected":    "Online",
    "disconnected": "Offline",
    "connecting":   "Connecting…",
    "error":        "Error",
}

LOG_TAG_COLOR = {
    "INFO":  None,             # default theme foreground
    "OK":    ACCENT_GREEN,
    "WARN":  ACCENT_AMBER,
    "ERROR": ACCENT_RED,
    "DEBUG": MUTED,
}


def _friendly_error(e: Exception) -> str:
    """Turn raw exception messages into plain-English hints."""
    import re
    msg = str(e)
    low = msg.lower()

    # Missing DLL — catches GPIB adapter drivers, Kinesis, Xeneth, etc.
    if "could not find module" in low and ".dll" in low:
        m = re.search(r"['\"]([^'\"]+\.dll)['\"]", msg)
        name = m.group(1).split("\\")[-1] if m else "a required DLL"
        nlow = name.lower()
        if "gpib" in nlow:
            return (f"Missing {name} — install NI-488.2 or Keysight IO Libraries "
                    f"for your GPIB-USB adapter")
        if "polarizer" in nlow or "kinesis" in nlow:
            return "Thorlabs Kinesis DLL not found — install Kinesis software"
        if "xeneth" in nlow or "xenics" in nlow:
            return f"Xeneth SDK not found ({name}) — install Xenics camera software"
        return f"Missing DLL: {name} — check driver installation"

    # Python-level gpib binding actually missing
    if "no module named 'gpib'" in low or "cannot import name 'gpib'" in low:
        return "Python GPIB binding missing — pip install gpib-ctypes"

    # gpib-ctypes installed but the system-level GPIB driver isn't loaded
    if "gpib library not found" in low or "manually load it using _load_lib" in low \
            or ("gpib" in low and "all gpib functions will raise" in low):
        return ("System GPIB driver not loaded — install NI-488.2 (free from ni.com) "
                "or Keysight IO Libraries for your GPIB-USB adapter, then reboot")

    # NI-VISA / pyvisa errors
    if "vi_error_rsrc_nfound" in low or "insufficient location information" in low:
        return ("VISA resource not found at that address — check the discovered "
                "resources logged below")
    if "vi_error_tmo" in low or ("timeout" in low and "visa" in low):
        return "VISA timeout — instrument may be off, busy, or at a different address"
    if "vi_error_nlisteners" in low:
        return "No GPIB listener at that address — wrong address, or instrument is off"
    if "vi_error_io" in low:
        return "VISA I/O error — check cable and instrument power"
    if "no gateway" in low and "visa" in low:
        return ("No VISA backend available — install NI-488.2 / Keysight IO Libraries, "
                "or 'pip install pyvisa-py'")

    # Serial / COM port
    if "could not open port" in low:
        port = re.search(r"'(COM\d+)'", msg)
        p = port.group(1) if port else "the COM port"
        return f"{p} not found or in use — is the device plugged in and the right port set in config?"

    if "polarizer.dll" in low or ("kinesis" in low and "dll" in low):
        return "Thorlabs Kinesis DLL not found — install Kinesis software and plug in motors"
    if "exposuretime" in low:
        return f"Camera property warning (may still work): {msg.splitlines()[0]}"

    # Fallback — strip giant tracebacks, keep first line
    return msg.split("\n")[0][:160]


# ── Application ───────────────────────────────────────────────────────────────

class HolographyApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Photonic Lantern Holography")
        self.root.geometry("1320x880")
        self.root.minsize(1100, 720)

        self.hardware_connected = False
        self.experiment_running = False
        self.stop_event = threading.Event()
        self.msg_queue: queue.Queue = queue.Queue()

        self.laser  = None
        self.camera = None
        self.switch = None
        self.motors = None
        self.config = self._load_config()

        self._setup_theme()
        self._build_ui()
        self._poll_queue()
        self._stop_background = threading.Event()
        threading.Thread(target=self._background_poller, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            import yaml
            with open(CONFIG_FILE) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    # ── Theme + fonts ─────────────────────────────────────────────────────────

    def _setup_theme(self):
        # Sun Valley (Windows 11 Fluent) — affects ttk widgets globally
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
        except Exception:
            pass  # falls back to default theme; app still works

        families = set(tkfont.families(self.root))
        body    = "Segoe UI Variable Text"    if "Segoe UI Variable Text"    in families else "Segoe UI"
        display = "Segoe UI Variable Display" if "Segoe UI Variable Display" in families else "Segoe UI"
        small   = "Segoe UI Variable Small"   if "Segoe UI Variable Small"   in families else "Segoe UI"
        mono    = "Cascadia Mono"             if "Cascadia Mono"             in families else "Consolas"

        self._font_body    = (body,    10)
        self._font_body_bold = (body,  10, "bold")
        self._font_section = (body,    11, "bold")
        self._font_title   = (display, 18)
        self._font_subtitle = (display, 11)
        self._font_metric  = (display, 13)
        self._font_small   = (small,    9)
        self._font_mono    = (mono,     9)

        self.root.option_add("*Font", f"{{{body}}} 10")

        # The Treeview heading font isn't picked up from option_add — set explicitly
        s = ttk.Style()
        s.configure("Treeview",          rowheight=26, font=self._font_body)
        s.configure("Treeview.Heading",  font=self._font_body_bold)
        # Reserve a card-ish frame style for grouped sections
        s.configure("Card.TFrame")  # sv-ttk already styles ttk.Frame nicely

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Title row
        title_row = ttk.Frame(self.root)
        title_row.pack(fill="x", padx=18, pady=(14, 4))
        ttk.Label(title_row, text="Photonic Lantern Holography",
                  font=self._font_title).pack(side="left")
        ttk.Label(title_row, text="UCF CREOL  ·  python main.py",
                  font=self._font_small, foreground=MUTED).pack(side="right")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=18, pady=(2, 8))

        self._build_hw_bar()

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=18, pady=(2, 12))

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(side="left", fill="both", expand=True)

        self._build_run_tab()
        self._build_laser_tab()
        self._build_switch_tab()
        self._build_polarization_tab()
        self._build_config_tab()
        self._build_results_tab()

        self._build_log_panel(main)

    # ── Hardware bar ──────────────────────────────────────────────────────────

    def _build_hw_bar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=18, pady=(0, 10))

        ttk.Label(bar, text="Hardware", font=self._font_section).pack(side="left", padx=(0, 18))

        self._hw_dots: dict        = {}
        self._hw_status_labels: dict = {}

        for name in ("Laser", "Camera", "Switch", "Motors"):
            cell = ttk.Frame(bar)
            cell.pack(side="left", padx=10)
            dot = ttk.Label(cell, text="●", foreground=MUTED, font=(self._font_body[0], 12))
            dot.pack(side="left")
            ttk.Label(cell, text=f"  {name}", font=self._font_body_bold).pack(side="left")
            status = ttk.Label(cell, text="  Offline", foreground=MUTED, font=self._font_small)
            status.pack(side="left")
            self._hw_dots[name.lower()]          = dot
            self._hw_status_labels[name.lower()] = status

        btn_row = ttk.Frame(bar)
        btn_row.pack(side="right")
        self._connect_btn = ttk.Button(btn_row, text="Connect All",
                                       style="Accent.TButton",
                                       command=self._connect_hardware)
        self._connect_btn.pack(side="left", padx=(0, 6))
        self._disconnect_btn = ttk.Button(btn_row, text="Disconnect",
                                          command=self._disconnect_hardware,
                                          state="disabled")
        self._disconnect_btn.pack(side="left")

    # ── Run tab ───────────────────────────────────────────────────────────────

    def _build_run_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Run Experiment")

        # Row 1 — mode selector + run controls
        ctrl = ttk.Frame(tab)
        ctrl.pack(fill="x", pady=(0, 12))

        ttk.Label(ctrl, text="Mode", font=self._font_body_bold).pack(side="left", padx=(0, 12))
        self._run_mode = tk.StringVar(value="full")
        for label, val in (("Collect", "collect"), ("Process", "process"), ("Full Run", "full")):
            ttk.Radiobutton(ctrl, text=label, variable=self._run_mode,
                            value=val).pack(side="left", padx=8)

        self._stop_btn = ttk.Button(ctrl, text="Stop",
                                    command=self._stop_experiment, state="disabled")
        self._stop_btn.pack(side="right", padx=(6, 0))
        self._start_btn = ttk.Button(ctrl, text="Start Experiment",
                                     style="Accent.TButton",
                                     command=self._start_experiment, state="disabled")
        self._start_btn.pack(side="right")

        ttk.Separator(tab, orient="horizontal").pack(fill="x", pady=(0, 10))

        # Row 2 — progress
        ttk.Label(tab, text="Progress", font=self._font_section).pack(anchor="w")
        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(tab, variable=self._progress_var,
                        maximum=100).pack(fill="x", pady=(6, 4))

        self._status_var = tk.StringVar(value="Connect hardware to begin")
        ttk.Label(tab, textvariable=self._status_var,
                  font=self._font_body).pack(anchor="w", pady=(0, 6))

        # Metric strip
        metrics = ttk.Frame(tab)
        metrics.pack(fill="x", pady=(0, 14))
        self._leg_var    = tk.StringVar(value="—")
        self._wl_var     = tk.StringVar(value="—")
        self._acq_var    = tk.StringVar(value="0 / 0")
        self._fringe_var = tk.StringVar(value="—")

        for col, (label, var) in enumerate((
            ("Leg",        self._leg_var),
            ("Wavelength", self._wl_var),
            ("Images",     self._acq_var),
            ("Fringe",     self._fringe_var),
        )):
            cell = ttk.Frame(metrics)
            cell.grid(row=0, column=col, sticky="w", padx=(0, 32))
            ttk.Label(cell, text=label.upper(), font=self._font_small,
                      foreground=MUTED).pack(anchor="w")
            ttk.Label(cell, textvariable=var, font=self._font_metric).pack(anchor="w")

        # Camera preview
        ttk.Label(tab, text="Camera Preview",
                  font=self._font_section).pack(anchor="w", pady=(2, 6))
        preview = ttk.Frame(tab)
        preview.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(preview, bg="#0a0a0a", highlightthickness=1,
                                 highlightbackground="#3a3a3a")
        self._canvas.pack(fill="both", expand=True)
        self._canvas_photo = None
        self._last_frame   = None
        self._canvas.bind("<Configure>", lambda _e: self._redraw_frame())
        self._canvas.create_text(220, 120, text="No signal",
                                 fill=MUTED, font=self._font_metric, tags="nosignal")

    # ── Laser tab ─────────────────────────────────────────────────────────────

    def _build_laser_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Laser")

        ttk.Label(tab, foreground=MUTED, font=self._font_small,
                  text="HP 8168E tunable laser. 1475–1575 nm, SCPI over GPIB."
                  ).pack(anchor="w", pady=(0, 12))

        big = (self._font_title[0], 26)

        # Wavelength card
        wl = ttk.LabelFrame(tab, text="  Wavelength  ", padding=14)
        wl.pack(fill="x", pady=6)
        self._laser_wl_cur = tk.StringVar(value="—")
        ttk.Label(wl, textvariable=self._laser_wl_cur, font=big,
                  width=10, anchor="w").pack(side="left", padx=(0, 20))
        ttk.Label(wl, text="nm", foreground=MUTED).pack(side="left", padx=(0, 16))
        ttk.Label(wl, text="Target", foreground=MUTED).pack(side="left", padx=(0, 6))
        self._laser_wl_target = tk.DoubleVar(value=1550.0)
        sp = ttk.Spinbox(wl, from_=1475, to=1575, increment=1.0,
                        textvariable=self._laser_wl_target, width=10, format="%.2f")
        sp.pack(side="left", padx=2)
        sp.bind("<Return>", lambda _e: self._set_laser_wavelength())
        ttk.Label(wl, text="nm", foreground=MUTED).pack(side="left", padx=(2, 6))
        ttk.Button(wl, text="Set λ", style="Accent.TButton",
                   command=self._set_laser_wavelength).pack(side="left", padx=2)

        # Power card
        pw = ttk.LabelFrame(tab, text="  Power  ", padding=14)
        pw.pack(fill="x", pady=6)
        self._laser_pw_cur = tk.StringVar(value="—")
        ttk.Label(pw, textvariable=self._laser_pw_cur, font=big,
                  width=10, anchor="w").pack(side="left", padx=(0, 20))
        ttk.Label(pw, text="µW", foreground=MUTED).pack(side="left", padx=(0, 16))
        ttk.Label(pw, text="Target", foreground=MUTED).pack(side="left", padx=(0, 6))
        self._laser_pw_target = tk.DoubleVar(value=208.0)
        sp2 = ttk.Spinbox(pw, from_=50, to=500, increment=10,
                          textvariable=self._laser_pw_target, width=10, format="%.0f")
        sp2.pack(side="left", padx=2)
        sp2.bind("<Return>", lambda _e: self._set_laser_power())
        ttk.Label(pw, text="µW", foreground=MUTED).pack(side="left", padx=(2, 6))
        ttk.Button(pw, text="Set P", style="Accent.TButton",
                   command=self._set_laser_power).pack(side="left", padx=2)

        # Output card
        out = ttk.LabelFrame(tab, text="  Output  ", padding=14)
        out.pack(fill="x", pady=6)
        self._laser_out_state = tk.StringVar(value="—")
        ttk.Label(out, textvariable=self._laser_out_state, font=big,
                  width=6, anchor="w").pack(side="left", padx=(0, 20))
        ttk.Button(out, text="Turn ON", style="Accent.TButton",
                   command=lambda: self._set_laser_output(True)).pack(side="left", padx=4)
        ttk.Button(out, text="Turn OFF",
                   command=lambda: self._set_laser_output(False)).pack(side="left", padx=4)

        self._laser_status_var = tk.StringVar(value="Connect to enable controls.")
        ttk.Label(tab, textvariable=self._laser_status_var,
                  foreground=MUTED, font=self._font_small).pack(anchor="w", pady=(14, 0))

    def _set_laser_wavelength(self):
        if not self.laser:
            self._laser_status_var.set("Laser not connected.")
            return
        threading.Thread(target=self._set_laser_wavelength_worker,
                         args=(float(self._laser_wl_target.get()),),
                         daemon=True).start()

    def _set_laser_wavelength_worker(self, target):
        try:
            self.laser.changeWavelength(target)
            self.msg_queue.put({"type": "log",
                                "text": f"Laser λ → {target:.2f} nm", "level": "INFO"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Set λ failed: {e}", "level": "WARN"})

    def _set_laser_power(self):
        if not self.laser:
            self._laser_status_var.set("Laser not connected.")
            return
        threading.Thread(target=self._set_laser_power_worker,
                         args=(float(self._laser_pw_target.get()),),
                         daemon=True).start()

    def _set_laser_power_worker(self, uw):
        try:
            self.laser.powerAmplitude(uw, "UW")
            self.msg_queue.put({"type": "log",
                                "text": f"Laser P → {uw:.0f} µW",
                                "level": "INFO"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Set P failed: {e}", "level": "WARN"})

    def _set_laser_output(self, on):
        if not self.laser:
            self._laser_status_var.set("Laser not connected.")
            return
        threading.Thread(target=self._set_laser_output_worker,
                         args=(on,), daemon=True).start()

    def _set_laser_output_worker(self, on):
        try:
            self.laser.outputState(on)
            self.msg_queue.put({"type": "log",
                                "text": f"Laser output {'ON' if on else 'OFF'}",
                                "level": "INFO"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Output toggle failed: {e}",
                                "level": "WARN"})

    # ── Switch tab ────────────────────────────────────────────────────────────

    def _build_switch_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Switch")

        ttk.Label(tab, foreground=MUTED, font=self._font_small,
                  text="Dicon GP700 fiber switch. Routes the input fiber to one of "
                       "N output ports (legs of the photonic lantern)."
                  ).pack(anchor="w", pady=(0, 12))

        big = (self._font_title[0], 26)

        pos = ttk.LabelFrame(tab, text="  Current leg  ", padding=14)
        pos.pack(fill="x", pady=6)
        self._switch_pos_cur = tk.StringVar(value="—")
        ttk.Label(pos, textvariable=self._switch_pos_cur, font=big,
                  width=4, anchor="w").pack(side="left", padx=(0, 20))
        ttk.Label(pos, text="Go to leg", foreground=MUTED).pack(side="left", padx=(0, 6))
        self._switch_pos_target = tk.IntVar(value=1)
        sp = ttk.Spinbox(pos, from_=1, to=16, increment=1,
                         textvariable=self._switch_pos_target, width=6)
        sp.pack(side="left", padx=2)
        sp.bind("<Return>", lambda _e: self._switch_to_leg(int(self._switch_pos_target.get())))
        ttk.Button(pos, text="Move", style="Accent.TButton",
                   command=lambda: self._switch_to_leg(int(self._switch_pos_target.get()))
                   ).pack(side="left", padx=(6, 2))

        quick = ttk.LabelFrame(tab, text="  Quick select  ", padding=14)
        quick.pack(fill="x", pady=6)
        legs = self.config.get("experiment", {}).get("legs", list(range(1, 8)))
        for leg in legs:
            ttk.Button(quick, text=f"Leg {leg}", width=8,
                       command=lambda l=leg: self._switch_to_leg(l)
                       ).pack(side="left", padx=4)

        self._switch_status_var = tk.StringVar(value="Connect to enable controls.")
        ttk.Label(tab, textvariable=self._switch_status_var,
                  foreground=MUTED, font=self._font_small).pack(anchor="w", pady=(14, 0))

    def _switch_to_leg(self, leg: int):
        if not self.switch:
            self._switch_status_var.set("Switch not connected.")
            return
        self._switch_pos_target.set(leg)
        threading.Thread(target=self._switch_to_leg_worker, args=(leg,),
                         daemon=True).start()

    def _switch_to_leg_worker(self, leg: int):
        try:
            module = self.config.get("hardware", {}).get("fiber_switch", {}).get("module", 1)
            self.switch.move_to_position(module, leg)
            self.msg_queue.put({"type": "log",
                                "text": f"Switch → leg {leg}",
                                "level": "INFO"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Switch move to leg {leg} failed: {e}",
                                "level": "WARN"})

    # ── Polarization tab ──────────────────────────────────────────────────────

    def _build_polarization_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Polarization")

        ttk.Label(tab, foreground=MUTED, font=self._font_small,
                  text="Three motorized paddles squeeze the fiber to tune polarization. "
                       "For holography you want signal and reference arms parallel — "
                       "max fringes.").pack(anchor="w", pady=(0, 12))

        # Global jog size — applies to all three paddles
        jog_row = ttk.Frame(tab)
        jog_row.pack(fill="x", pady=(0, 10))
        ttk.Label(jog_row, text="Jog size", font=self._font_body).pack(side="left")
        self._jog_size_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(jog_row, from_=0.1, to=10.0, increment=0.5,
                    textvariable=self._jog_size_var,
                    width=6, format="%.1f").pack(side="left", padx=(8, 2))
        ttk.Label(jog_row, text="°", foreground=MUTED).pack(side="left")

        self._paddle_cur_vars:    dict = {}
        self._paddle_target_vars: dict = {}

        big_font = (self._font_title[0], 30)

        for i in (1, 2, 3):
            card = ttk.LabelFrame(tab, text=f"  Paddle {i}  ", padding=14)
            card.pack(fill="x", pady=6)

            # Left: big current-angle readout
            cur_var = tk.StringVar(value="—")
            self._paddle_cur_vars[i] = cur_var
            ttk.Label(card, textvariable=cur_var, font=big_font,
                      width=7, anchor="w").pack(side="left", padx=(0, 20))

            # Right: stacked control rows
            right = ttk.Frame(card)
            right.pack(side="left", fill="x", expand=True)

            top = ttk.Frame(right)
            top.pack(fill="x")
            ttk.Label(top, text="Target", foreground=MUTED).pack(side="left", padx=(0, 6))
            target_var = tk.DoubleVar(value=0.0)
            self._paddle_target_vars[i] = target_var
            sp = ttk.Spinbox(top, from_=0, to=160, increment=1.0,
                             textvariable=target_var, width=8, format="%.1f")
            sp.pack(side="left", padx=2)
            sp.bind("<Return>", lambda _e, p=i: self._move_paddle(p))
            ttk.Button(top, text="Move To", style="Accent.TButton",
                       command=lambda p=i: self._move_paddle(p)).pack(side="left", padx=(6, 4))
            ttk.Button(top, text="Home",
                       command=lambda p=i: self._home_paddle(p)).pack(side="left", padx=2)

            bot = ttk.Frame(right)
            bot.pack(fill="x", pady=(8, 0))
            ttk.Button(bot, text="«  Jog", width=10,
                       command=lambda p=i: self._jog_paddle(p, -1)).pack(side="left", padx=(0, 4))
            ttk.Button(bot, text="Jog  »", width=10,
                       command=lambda p=i: self._jog_paddle(p, +1)).pack(side="left")

        ttk.Separator(tab, orient="horizontal").pack(fill="x", pady=(14, 10))

        ctrl = ttk.Frame(tab)
        ctrl.pack(fill="x")
        ttk.Button(ctrl, text="Home all",
                   command=self._home_all_paddles).pack(side="left")
        self._pol_optimize_btn = ttk.Button(
            ctrl, text="Auto-optimize for fringes",
            style="Accent.TButton",
            command=self._auto_optimize_polarization)
        self._pol_optimize_btn.pack(side="left", padx=8)

        self._pol_status_var = tk.StringVar(value="Connect motors to enable controls.")
        ttk.Label(tab, textvariable=self._pol_status_var,
                  foreground=MUTED, font=self._font_small).pack(anchor="w", pady=(10, 0))

    def _background_poller(self):
        """Single daemon thread that reads hardware state and posts
        updates to the message queue. Keeps blocking SDK calls (GPIB
        queries, serial reads) off the Tk main thread so the GUI
        never freezes."""
        tick = 0
        while not self._stop_background.is_set():
            # Paddles — fast (Kinesis returns from its own cache)
            if self.motors:
                for i in (1, 2, 3):
                    try:
                        a = self.motors.getPosition(i)
                        self.msg_queue.put({"type": "paddle_pos", "paddle": i, "value": a})
                    except Exception:
                        pass

            # Laser — every ~3 s (GPIB roundtrip per query, slow)
            if tick % 10 == 0 and self.laser:
                try:
                    wl = self.laser.checkWavelength()
                    self.msg_queue.put({"type": "laser_wl", "value": wl})
                except Exception:
                    pass
                try:
                    pw = self.laser.checkPowerAmplitude()
                    self.msg_queue.put({"type": "laser_pw", "value": pw})
                except Exception:
                    pass
                try:
                    on = self.laser.isOutputOn()
                    self.msg_queue.put({"type": "laser_out", "value": on})
                except Exception:
                    pass

            # Switch — every ~2.4 s (serial roundtrip)
            if tick % 8 == 0 and self.switch:
                try:
                    module = self.config.get("hardware", {}).get(
                        "fiber_switch", {}).get("module", 1)
                    pos = self.switch.get_position(module)
                    if pos is not None:
                        self.msg_queue.put({"type": "switch_pos", "value": pos})
                except Exception:
                    pass

            tick += 1
            self._stop_background.wait(0.3)

    def _sync_paddle_targets_from_hw(self):
        """Set slider targets to whatever the motors currently report."""
        if not self.motors or not hasattr(self, "_paddle_target_vars"):
            return
        for i in (1, 2, 3):
            try:
                a = (self.motors.getPosition(i)
                     if hasattr(self.motors, "getPosition")
                     else self.motors.angles[i - 1])
                self._paddle_target_vars[i].set(float(a))
            except Exception:
                pass
        self._pol_status_var.set("Ready.")

    def _move_paddle(self, paddle: int):
        if not self.motors:
            self._pol_status_var.set("Motors not connected.")
            return
        target = float(self._paddle_target_vars[paddle].get())
        target = max(0.0, min(160.0, target))
        threading.Thread(target=self._move_paddle_worker,
                         args=(paddle, target), daemon=True).start()

    def _move_paddle_worker(self, paddle: int, target: float):
        try:
            self.motors.moveMotor(paddle, target)
            self.msg_queue.put({"type": "log",
                                "text": f"Paddle {paddle} → {target:.1f}°",
                                "level": "INFO"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Paddle {paddle} move failed: {e}",
                                "level": "WARN"})

    def _home_paddle(self, paddle: int):
        if not self.motors:
            self._pol_status_var.set("Motors not connected.")
            return
        self._paddle_target_vars[paddle].set(0.0)
        threading.Thread(target=self._home_paddle_worker,
                         args=(paddle,), daemon=True).start()

    def _home_paddle_worker(self, paddle: int):
        try:
            start = (self.motors.getPosition(paddle)
                     if hasattr(self.motors, "getPosition") else None)
            if hasattr(self.motors, "homeMotor"):
                self.motors.homeMotor(paddle)
            else:
                self.motors.moveMotor(paddle, 0.0)
            # Home is a calibration sweep, not a fast move — wait until the
            # motor is no longer busy before sampling final position (cap 30s)
            time.sleep(0.5)
            deadline = time.time() + 30
            while time.time() < deadline and self.motors.isBusy():
                time.sleep(0.2)
            actual = (self.motors.getPosition(paddle)
                      if hasattr(self.motors, "getPosition") else 0.0)
            ok = abs(actual) < 2.0
            extra = "" if start is None else f"  (from {start:.1f}°)"
            self.msg_queue.put({
                "type": "log",
                "text": f"Paddle {paddle} home → now {actual:.1f}°{extra}"
                        + ("" if ok else "  ⚠ didn't reach 0°"),
                "level": "INFO" if ok else "WARN",
            })
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Paddle {paddle} home failed: {e}",
                                "level": "WARN"})

    def _jog_paddle(self, paddle: int, direction: int):
        if not self.motors:
            self._pol_status_var.set("Motors not connected.")
            return
        try:
            step = float(self._jog_size_var.get())
        except (tk.TclError, ValueError):
            step = 1.0
        # Jog from the actual hardware position if available so repeated
        # clicks compound on the real angle, not on a stale slider value
        try:
            cur = (self.motors.getPosition(paddle)
                   if hasattr(self.motors, "getPosition")
                   else self.motors.angles[paddle - 1])
        except Exception:
            cur = float(self._paddle_target_vars[paddle].get())
        new = max(0.0, min(160.0, cur + direction * step))
        self._paddle_target_vars[paddle].set(new)
        self._move_paddle(paddle)

    def _home_all_paddles(self):
        if not self.motors:
            self._pol_status_var.set("Motors not connected.")
            return
        for i in (1, 2, 3):
            self._home_paddle(i)

    def _auto_optimize_polarization(self):
        if not self.motors:
            self._pol_status_var.set("Motors not connected.")
            return
        if not self.camera:
            self._pol_status_var.set("Camera needed for fringe-based optimization.")
            return
        if self.experiment_running:
            self._pol_status_var.set("Stop the experiment first.")
            return
        self._pol_optimize_btn.configure(state="disabled")
        self._pol_status_var.set("Sweeping paddles — this can take a minute…")
        threading.Thread(target=self._auto_optimize_worker, daemon=True).start()

    def _auto_optimize_worker(self):
        try:
            from fringe_detection import optimize_polarization_for_fringes
            fd = self.config.get("experiment", {}).get("fringe_detection", {})
            success, metric, angles = optimize_polarization_for_fringes(
                self.camera, self.motors,
                max_attempts=int(fd.get("max_attempts", 30)),
                method=fd.get("check_method", "variance"),
                threshold=float(fd.get("min_visibility", 0.15)),
            )
            tag = "OK" if success else "WARN"
            mark = "✓" if success else "⚠"
            msg = (f"{mark} Auto-optimize: paddles={[round(a, 1) for a in angles]}, "
                   f"metric={metric:.3f}"
                   + ("" if success else
                      f"  (below threshold {fd.get('min_visibility', 0.15)})"))
            self.msg_queue.put({"type": "log", "text": msg, "level": tag})
            self._pol_status_var.set(msg)
            self._sync_paddle_targets_from_hw()
        except Exception as e:
            import traceback
            self.msg_queue.put({"type": "log",
                                "text": f"Auto-optimize failed: {e}",
                                "level": "ERROR"})
            self.msg_queue.put({"type": "log", "text": traceback.format_exc(),
                                "level": "DEBUG"})
            self._pol_status_var.set(f"Failed: {e}")
        finally:
            self._pol_optimize_btn.configure(state="normal")

    # ── Config tab ────────────────────────────────────────────────────────────

    def _build_config_tab(self):
        tab = ttk.Frame(self.notebook, padding=(2, 4))
        self.notebook.add(tab, text="Configuration")

        # Scrollable container — Canvas + inner Frame
        outer = tk.Canvas(tab, highlightthickness=0, background="#1c1c1c")
        vsb   = ttk.Scrollbar(tab, orient="vertical", command=outer.yview)
        outer.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        outer.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(outer, padding=14)
        inner.bind("<Configure>",
                   lambda e: outer.configure(scrollregion=outer.bbox("all")))
        outer.create_window((0, 0), window=inner, anchor="nw")

        self._cfg_vars: dict = {}

        def section(title: str, pad_top: int = 14):
            ttk.Label(inner, text=title, font=self._font_section).pack(
                anchor="w", pady=(pad_top, 6))

        def field(label: str, key: str, default):
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=32, anchor="w",
                      font=self._font_body).pack(side="left")
            var = tk.StringVar(value=str(default))
            ttk.Entry(row, textvariable=var, width=44).pack(side="left", padx=6)
            self._cfg_vars[key] = var

        hw  = self.config.get("hardware", {})
        exp = self.config.get("experiment", {})

        section("Hardware", pad_top=0)
        field("Laser GPIB address",          "hardware.laser.gpib_address",
              hw.get("laser", {}).get("gpib_address", "GPIB0::24::INSTR"))
        field("Laser power (µW)",            "hardware.laser.power_uw",
              hw.get("laser", {}).get("power_uw", 208))
        field("Camera URL",                  "hardware.camera.url",
              hw.get("camera", {}).get("url", "cam://0"))
        field("Camera exposure (µs)",        "hardware.camera.exposure_time",
              hw.get("camera", {}).get("exposure_time", 500))
        field("Fiber switch COM port",       "hardware.fiber_switch.port",
              hw.get("fiber_switch", {}).get("port", "COM6"))
        field("Motor serial number",         "hardware.polarization_motors.serial_number",
              hw.get("polarization_motors", {}).get("serial_number", "38394984"))

        section("Experiment")
        legs = exp.get("legs", list(range(1, 8)))
        field("Legs",                        "experiment.legs",
              ",".join(map(str, legs)))
        wls = exp.get("wavelengths", [1540, 1545, 1550, 1555, 1560, 1565, 1570])
        field("Wavelengths (nm)",            "experiment.wavelengths",
              ",".join(map(str, wls)))
        wt = exp.get("wait_times", {})
        field("Wait after leg switch (s)",   "experiment.wait_times.after_leg_switch",
              wt.get("after_leg_switch", 1.0))
        field("Wait after wavelength (s)",   "experiment.wait_times.after_wavelength_change",
              wt.get("after_wavelength_change", 0.5))
        fd = exp.get("fringe_detection", {})
        field("Min fringe visibility",       "experiment.fringe_detection.min_visibility",
              fd.get("min_visibility", 0.15))
        field("Max polarization attempts",   "experiment.fringe_detection.max_attempts",
              fd.get("max_attempts", 5))

        section("Output")
        field("Data output directory",       "data.output_dir",
              self.config.get("data", {}).get("output_dir", "./holography_data"))

        ttk.Button(inner, text="Save configuration", style="Accent.TButton",
                   command=self._save_config).pack(anchor="w", pady=(16, 4))

    # ── Results tab ───────────────────────────────────────────────────────────

    def _build_results_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Results")

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_row, text="Open data folder",
                   command=self._open_data_folder).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Refresh",
                   command=self._refresh_results).pack(side="left")

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)

        cols = ("file", "fidelity", "mode_powers")
        self._results_tree = ttk.Treeview(body, columns=cols, show="headings", height=24)
        self._results_tree.heading("file",        text="Hologram")
        self._results_tree.heading("fidelity",    text="Fidelity")
        self._results_tree.heading("mode_powers", text="Mode powers (LP01 → LP06)")
        self._results_tree.column("file",        width=240)
        self._results_tree.column("fidelity",    width=90, anchor="e")
        self._results_tree.column("mode_powers", width=400)

        vsb = ttk.Scrollbar(body, orient="vertical", command=self._results_tree.yview)
        self._results_tree.configure(yscrollcommand=vsb.set)
        self._results_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ── Log panel ─────────────────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        pane = ttk.Frame(parent, padding=(14, 0, 0, 0))
        pane.pack(side="right", fill="both")

        hdr = ttk.Frame(pane)
        hdr.pack(fill="x", pady=(0, 6))
        ttk.Label(hdr, text="Activity",
                  font=self._font_section).pack(side="left")
        ttk.Button(hdr, text="Clear",
                   command=self._clear_log).pack(side="right")

        # ScrolledText is plain tk — pick a bg that matches the theme
        log_bg = "#1a1a1a"   # sits a touch darker than sv-ttk dark background
        log_fg = "#e6e6e6"

        self._log_widget = scrolledtext.ScrolledText(
            pane, width=48, height=10,
            bg=log_bg, fg=log_fg,
            font=self._font_mono,
            state="disabled", wrap="word",
            insertbackground=log_fg,
            relief="flat", borderwidth=0,
            padx=10, pady=8,
        )
        self._log_widget.pack(fill="both", expand=True)

        for tag, color in LOG_TAG_COLOR.items():
            if color:
                self._log_widget.tag_config(tag, foreground=color)
            else:
                self._log_widget.tag_config(tag, foreground=log_fg)

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
                elif t == "paddle_pos":
                    p, v = msg["paddle"], msg["value"]
                    if hasattr(self, "_paddle_cur_vars") and p in self._paddle_cur_vars:
                        self._paddle_cur_vars[p].set(f"{v:.1f}°")
                elif t == "laser_wl":
                    v = msg["value"]
                    if isinstance(v, (int, float)):
                        self._laser_wl_cur.set(f"{v:.2f}")
                elif t == "laser_pw":
                    raw = str(msg["value"])
                    try:
                        v = float(raw)
                        # 8168E reports :POW? as watts (e.g. "2.08e-04"); some
                        # configurations return dBm or µW directly.
                        if "e" in raw.lower() or abs(v) < 0.1:
                            uw = v * 1e6                  # watts
                        elif abs(v) < 50:
                            uw = 10 ** (v / 10) * 1000    # dBm
                        else:
                            uw = v                        # already µW
                        self._laser_pw_cur.set(f"{uw:.0f}")
                    except (TypeError, ValueError):
                        pass
                elif t == "laser_out":
                    self._laser_out_state.set("ON" if "1" in str(msg["value"]) else "OFF")
                elif t == "switch_pos":
                    self._switch_pos_cur.set(str(msg["value"]))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ── Hardware dots ─────────────────────────────────────────────────────────

    def _set_hw_dot(self, device: str, status: str):
        dot = self._hw_dots.get(device)
        if dot:
            dot.configure(foreground=HW_STATUS_COLOR.get(status, MUTED))
        label = self._hw_status_labels.get(device)
        if label:
            label.configure(text=f"  {HW_STATUS_TEXT.get(status, '—')}",
                            foreground=HW_STATUS_COLOR.get(status, MUTED))

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

            # Fit image while preserving aspect ratio
            ih, iw = arr.shape
            scale = min(cw / iw, ch / ih)
            tw, th = max(int(iw * scale), 1), max(int(ih * scale), 1)

            img   = Image.fromarray(arr, mode="L").resize((tw, th), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._canvas.delete("nosignal")
            self._canvas.delete("frame")
            self._canvas.create_image(cw // 2, ch // 2, anchor="center",
                                      image=photo, tags="frame")
            self._canvas_photo = photo  # prevent GC
        except Exception:
            pass

    # ── Connect / disconnect ──────────────────────────────────────────────────

    def _connect_hardware(self):
        self._connect_btn.configure(state="disabled")
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
        self.msg_queue.put({"type": "done", "event": "connect", "success": True})

    def _emit(self, text, level="INFO"):
        self.msg_queue.put({"type": "log", "text": text, "level": level})

    def _hw(self, device, status):
        self.msg_queue.put({"type": "hw_status", "device": device, "status": status})

    def _connect_laser(self, record_ok, record_fail):
        self._hw("laser", "connecting")
        cfg_l = self.config.get("hardware", {}).get("laser", {})
        addr  = cfg_l.get("gpib_address", "GPIB0::24::INSTR")
        self._emit(f"Laser — trying {addr}…")
        try:
            from HPTunableLaserSource import HPTunableLaserSource
            self.laser = HPTunableLaserSource(addr)
            self.laser.changePowerUnit(cfg_l.get("power_unit", "UW"))
            power_uw = float(cfg_l.get("power_uw", 208))
            self.laser.powerAmplitude(power_uw, "UW")
            self.laser.outputState(True)
            self._hw("laser", "connected")
            self._emit(f"✓ Laser  {addr}  output ON  ({power_uw:.0f} µW)", "OK")
            record_ok("Laser")
        except Exception as e:
            self._hw("laser", "error")
            self._emit(f"✗ Laser — {_friendly_error(e)}", "WARN")
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
            self.camera = xCam(url=url)
            ser = int(self.camera.ser) if self.camera.ser else "?"
            self._hw("camera", "connected")
            self._emit(f"✓ Camera  Xenics Bobcat 320 GigE  SER:{ser}", "OK")
            record_ok("Camera")
            frame = self.camera.getFrame()
            if frame is not None:
                self.msg_queue.put({"type": "frame", "data": frame})
            else:
                self._emit("  (no frame yet — need light on sensor)", "DEBUG")
        except Exception as e:
            self._hw("camera", "error")
            self._emit(f"✗ Camera — {_friendly_error(e)}", "WARN")
            record_fail("Camera")

    def _connect_switch(self, record_ok, record_fail):
        self._hw("switch", "connecting")
        cfg_s = self.config.get("hardware", {}).get("fiber_switch", {})
        port  = cfg_s.get("port", "COM6")
        self._emit(f"Fiber switch — trying {port}…")
        try:
            from D700DiconSwitch import D700DiconSwitch
            self.switch = D700DiconSwitch(port=port, baudrate=cfg_s.get("baudrate", 9600))
            self._hw("switch", "connected")
            self._emit(f"✓ Switch  Dicon GP700  {port}", "OK")
            record_ok("Switch")
        except Exception as e:
            self._hw("switch", "error")
            self._emit(f"✗ Switch — {_friendly_error(e)}", "WARN")
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
            # Don't auto-home or auto-move — that puts paddle 3 in a
            # state where subsequent moves are ignored on this firmware.
            # User can home via the Polarization tab Home buttons.
            self._hw("motors", "connected")
            self._emit(f"✓ Motors  Thorlabs MPC320  SN:{serial}  connected", "OK")
            # Per-paddle diagnostic so we can see whether each paddle is
            # actually being addressed correctly by the SDK
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
            self._emit(f"✗ Motors — {_friendly_error(e)}", "WARN")
            record_fail("Motors")

    def _disconnect_hardware(self):
        if self.experiment_running:
            self._stop_experiment()
            time.sleep(0.5)

        self._log("Disconnecting hardware…", "INFO")
        for obj, method in [
            (self.laser,  lambda: (self.laser.outputState(False), self.laser.closeConnection())),
            (self.camera, lambda: (self.camera.stopCapture(), self.camera.closeCamera())),
            (self.switch, lambda: self.switch.close()),
            (self.motors, lambda: self.motors.close()),
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

    def _on_close(self):
        """Window close: stop experiment, disconnect hardware, then exit."""
        self._stop_background.set()
        if self.experiment_running:
            self.stop_event.set()
        for obj, method in [
            (self.laser,  lambda: (self.laser.outputState(False), self.laser.closeConnection())),
            (self.camera, lambda: (self.camera.stopCapture(), self.camera.closeCamera())),
            (self.switch, lambda: self.switch.close()),
            (self.motors, lambda: self.motors.close()),
        ]:
            if obj:
                try: method()
                except Exception: pass
        self.root.destroy()

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

        if not self.camera:
            cb({"type": "log",
                "text": "Camera not connected — cannot collect.", "level": "ERROR"})
            return
        if not self.switch and len(legs) > 1:
            cb({"type": "log",
                "text": f"Switch not connected — all {len(legs)} legs will be saved at the current optical path.",
                "level": "WARN"})
        if not self.laser and len(wls) > 1:
            cb({"type": "log",
                "text": f"Laser not connected — all {len(wls)} wavelengths will be saved at the current λ.",
                "level": "WARN"})

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
            ok    = getattr(self, "_connected_names", [])
            all_4 = ("Laser", "Camera", "Switch", "Motors")
            off   = [d for d in all_4 if d not in ok]

            self._connect_btn.configure(state="disabled")
            self._disconnect_btn.configure(state="normal")

            if len(ok) == 4:
                self._status_var.set("All 4 devices connected — ready to run")
                self._log("All hardware connected. Press ▶ START when ready.", "OK")
            elif len(ok) == 0:
                self._status_var.set("No devices connected — check cables & config")
                self._log("No devices connected. Check cables, COM ports, and GPIB address.", "ERROR")
                # Re-enable connect so they can retry after fixing things
                self._connect_btn.configure(state="normal")
                self._disconnect_btn.configure(state="disabled")
            else:
                summary = f"{len(ok)}/4 connected: {', '.join(ok)}"
                missing = f"Offline: {', '.join(off)}"
                self._status_var.set(f"{summary} — {missing}")
                self._log(f"{summary}", "OK")
                self._log(f"{missing} — plug in and click Connect to retry", "WARN")

            # Enable START as long as something is connected
            self._start_btn.configure(state="normal" if ok else "disabled")
            # Initialize Polarization tab slider targets from the actual angles
            if "Motors" in ok:
                self._sync_paddle_targets_from_hw()
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
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

        self.config = self._load_config()
        self._log("Configuration saved", "OK")
        messagebox.showinfo("Saved", "Configuration saved to experiment_config.yaml")

    # ── Results ───────────────────────────────────────────────────────────────

    def _open_data_folder(self):
        d = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d.absolute()))
        except Exception as e:
            self._log(f"Could not open folder: {e}", "WARN")

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

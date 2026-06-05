# -*- coding: utf-8 -*-
"""Window scaffolding shared by the whole app: config load, the title/hardware
bar, the notebook assembly, the Activity log panel, the message-queue pump that
marshals worker-thread updates onto the Tk thread, and the background hardware
poller."""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

from . import runtime
from .runtime import CONFIG_FILE
from .theme import MUTED, HW_STATUS_COLOR, HW_STATUS_TEXT, LOG_TAG_COLOR


class ShellMixin:
    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            import yaml
            with open(CONFIG_FILE) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

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
        # Mirror every Activity message into the session logfile (with level),
        # so there's a full on-disk record to read back if things go sideways.
        runtime.log_line(ts, level, text)

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
                        # Seed the target box from the laser's actual value the
                        # first time we read it (not the placeholder default).
                        if not self._laser_wl_target_init:
                            self._laser_wl_target.set(round(float(v), 2))
                            self._laser_wl_target_init = True
                elif t == "laser_pw":
                    raw = str(msg["value"])
                    try:
                        v = float(raw)
                        # The 8168 may report :POW? in dBm, watts, or µW
                        # depending on its unit setting. Infer from SIGN and
                        # MAGNITUDE, not text format — µW/watts are always
                        # positive, so anything negative is dBm. (The old
                        # "'e' in string => watts" check turned a dBm value
                        # like "-3.01E0" into -3,010,300.)
                        if v < 0:
                            uw = 10 ** (v / 10) * 1000    # negative => dBm
                        elif abs(v) < 1e-2:
                            uw = v * 1e6                  # tiny +ve => watts
                        elif v < 10:
                            uw = 10 ** (v / 10) * 1000    # small +ve => dBm (e.g. +2 dBm)
                        else:
                            uw = v                        # already µW
                        self._laser_pw_cur.set(f"{uw:.0f}")
                        if not self._laser_pw_target_init:
                            self._laser_pw_target.set(round(uw))
                            self._laser_pw_target_init = True
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

    # ── Background hardware poller ──────────────────────────────────────────────

    def _mark_user_action(self):
        """Stamp the last-user-action time so the background poller
        backs off briefly and the user's GPIB/serial command isn't
        stuck behind a poll already in flight."""
        self._user_action_time = time.monotonic()

    def _background_poller(self):
        """Single daemon thread that reads hardware state and posts
        updates to the message queue. Keeps blocking SDK calls (GPIB
        queries, serial reads) off the Tk main thread so the GUI
        never freezes."""
        tick = 0
        self._user_action_time = 0.0
        while not self._stop_background.is_set():
            user_busy = (time.monotonic() - self._user_action_time) < 1.5

            # Paddles — fast (Kinesis returns from its own cache)
            if self.motors:
                for i in (1, 2, 3):
                    try:
                        a = self.motors.getPosition(i)
                        self.msg_queue.put({"type": "paddle_pos", "paddle": i, "value": a})
                    except Exception:
                        pass

            # Laser — staggered: each query on its own tick so one cycle is short
            if self.laser and not user_busy:
                slot = tick % 10
                try:
                    if slot == 0:
                        wl = self.laser.checkWavelength()
                        self.msg_queue.put({"type": "laser_wl", "value": wl})
                    elif slot == 3:
                        pw = self.laser.checkPowerAmplitude()
                        self.msg_queue.put({"type": "laser_pw", "value": pw})
                    elif slot == 6:
                        on = self.laser.isOutputOn()
                        self.msg_queue.put({"type": "laser_out", "value": on})
                except Exception:
                    pass

            # Switch — every ~2.4 s (serial roundtrip)
            if tick % 8 == 0 and self.switch and not user_busy:
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

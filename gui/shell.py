# -*- coding: utf-8 -*-
"""Window scaffolding shared by the whole app: config load, the title/hardware
bar, the tab assembly, the Activity log panel, the signal dispatch slot that
marshals worker-thread messages onto the GUI thread, and the background
hardware poller."""

import html
import threading
import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import runtime
from .runtime import CONFIG_FILE
from .style import MUTED, FG, HW_STATUS_COLOR, HW_STATUS_TEXT, LOG_TAG_COLOR


class ShellMixin:
    # ── Config ──────────────────────────────────────────────────────────────
    def _load_config(self) -> dict:
        try:
            import yaml
            with open(CONFIG_FILE) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            return {}
        # Normalize legs/wavelengths so downstream `for x in ...` loops are safe:
        #  - a {start, stop, step} dict expands to an inclusive list (lets you
        #    write a sweep as a range instead of listing every value);
        #  - a bare scalar becomes a one-element list (the Config tab can save
        #    "1" as int 1, which would otherwise crash every loop).
        exp = cfg.get("experiment")
        if isinstance(exp, dict):
            for key in ("legs", "wavelengths"):
                v = exp.get(key)
                if isinstance(v, dict) and "start" in v and "stop" in v:
                    exp[key] = self._expand_range(v)
                elif v is not None and not isinstance(v, (list, tuple)):
                    exp[key] = [v]
        return cfg

    @staticmethod
    def _expand_range(spec: dict) -> list:
        """Expand {start, stop, step} into an inclusive numeric list.
        e.g. {start: 1525, stop: 1575, step: 5} -> [1525, 1530, ... 1575]."""
        try:
            start = float(spec["start"]); stop = float(spec["stop"])
            step = abs(float(spec.get("step", 1) or 1)) or 1.0
        except (TypeError, ValueError):
            return []
        if stop < start:
            step = -step
        n = int(round((stop - start) / step)) + 1
        out = []
        for i in range(max(n, 1)):
            x = start + i * step
            out.append(int(round(x)) if float(x).is_integer() else round(x, 4))
        return out

    # ── UI construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(8)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Photonic Lantern Holography"); title.setObjectName("Title")
        sub = QLabel("UCF CREOL  ·  python main.py"); sub.setObjectName("Small")
        title_row.addWidget(title); title_row.addStretch(1); title_row.addWidget(sub)
        root.addLayout(title_row)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet(f"color:{MUTED}")
        root.addWidget(line)

        self._build_hw_bar(root)

        main = QHBoxLayout(); root.addLayout(main, 1)
        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)

        self._build_run_tab()
        self._build_laser_tab()
        self._build_switch_tab()
        self._build_polarization_tab()
        self._build_config_tab()
        self._build_results_tab()

        self._build_log_panel(main)

    # ── Hardware bar ──────────────────────────────────────────────────────────
    def _build_hw_bar(self, root):
        bar = QHBoxLayout()
        lbl = QLabel("Hardware"); lbl.setObjectName("Section")
        bar.addWidget(lbl); bar.addSpacing(18)

        self._hw_dots: dict = {}
        self._hw_status_labels: dict = {}
        self._hw_connect_btns: dict = {}
        for name in ("Laser", "Camera", "Switch", "Motors"):
            dot = QLabel("●"); dot.setStyleSheet(f"color:{MUTED}; font-size:12pt")
            # The device name is a flat button: click it to connect ONLY that
            # device. Lets you drive e.g. the switch + laser from the app while
            # Xeneth keeps the camera (GigE needs a single owner of the stream).
            nm  = QPushButton(name); nm.setFlat(True)
            nm.setToolTip(f"Connect only the {name.lower()}")
            nm.clicked.connect(lambda _checked=False, d=name: self._connect_hardware([d]))
            st  = QLabel("Offline"); st.setObjectName("Small")
            bar.addWidget(dot); bar.addWidget(nm); bar.addWidget(st); bar.addSpacing(12)
            self._hw_dots[name.lower()] = dot
            self._hw_status_labels[name.lower()] = st
            self._hw_connect_btns[name.lower()] = nm

        bar.addStretch(1)
        self._connect_btn = QPushButton("Connect All"); self._connect_btn.setObjectName("Accent")
        self._connect_btn.clicked.connect(lambda: self._connect_hardware())
        self._disconnect_btn = QPushButton("Disconnect"); self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._disconnect_hardware)
        bar.addWidget(self._connect_btn); bar.addWidget(self._disconnect_btn)
        root.addLayout(bar)

    # ── Log panel ──────────────────────────────────────────────────────────────
    def _build_log_panel(self, main):
        pane = QVBoxLayout()
        hdr = QHBoxLayout()
        h = QLabel("Activity"); h.setObjectName("Section")
        clear = QPushButton("Clear"); clear.clicked.connect(self._clear_log)
        hdr.addWidget(h); hdr.addStretch(1); hdr.addWidget(clear)
        pane.addLayout(hdr)

        self._log_widget = QTextEdit(); self._log_widget.setObjectName("Log")
        self._log_widget.setReadOnly(True)
        self._log_widget.setMinimumWidth(360)
        pane.addWidget(self._log_widget, 1)

        wrap = QWidget(); wrap.setLayout(pane); wrap.setFixedWidth(380)
        main.addWidget(wrap)

    # ── Logging (GUI thread only) ───────────────────────────────────────────────
    def _log(self, text: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        color = LOG_TAG_COLOR.get(level, FG)
        safe = html.escape(f"[{ts}] {text}")
        self._log_widget.append(f'<span style="color:{color}">{safe}</span>')
        runtime.log_line(ts, level, text)

    def _clear_log(self):
        self._log_widget.clear()

    # ── Signal dispatch (runs on GUI thread) ────────────────────────────────────
    def _dispatch_msg(self, msg: dict):
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
            lbl = getattr(self, "_paddle_cur_lbls", {}).get(p)
            if lbl:
                lbl.setText(f"{v:.1f}°")
        elif t == "laser_wl":
            v = msg["value"]
            if isinstance(v, (int, float)):
                self._laser_wl_cur_lbl.setText(f"{v:.2f}")
                if not self._laser_wl_target_init:
                    self._laser_wl_spin.setValue(round(float(v), 2))
                    self._laser_wl_target_init = True
        elif t == "laser_pw":
            self._update_laser_power_readout(msg["value"])
        elif t == "laser_out":
            self._laser_out_lbl.setText("ON" if "1" in str(msg["value"]) else "OFF")
        elif t == "switch_pos":
            self._switch_pos_cur_lbl.setText(str(msg["value"]))
        elif t == "pol_status":
            self._pol_status_lbl.setText(msg["text"])
        elif t == "pol_optimize_done":
            # Back on the GUI thread: re-enable the buttons and refresh the
            # paddle spin targets from the motors' real angles.
            self._pol_optimize_btn.setEnabled(True)
            self._pol_balance_btn.setEnabled(True)
            self._sync_paddle_targets_from_hw()

    def _update_laser_power_readout(self, raw):
        try:
            v = float(str(raw))
            # The 8168 may report :POW? in dBm, watts, or µW. Infer from sign
            # and magnitude, not text format (negative => dBm; tiny +ve =>
            # watts; small +ve => dBm; else already µW).
            if v < 0:
                uw = 10 ** (v / 10) * 1000
            elif abs(v) < 1e-2:
                uw = v * 1e6
            elif v < 10:
                uw = 10 ** (v / 10) * 1000
            else:
                uw = v
            self._laser_pw_cur_lbl.setText(f"{uw:.0f}")
            if not self._laser_pw_target_init:
                self._laser_pw_spin.setValue(round(uw))
                self._laser_pw_target_init = True
        except (TypeError, ValueError):
            pass

    # ── Hardware dots ───────────────────────────────────────────────────────────
    def _set_hw_dot(self, device: str, status: str):
        color = HW_STATUS_COLOR.get(status, MUTED)
        dot = self._hw_dots.get(device)
        if dot:
            dot.setStyleSheet(f"color:{color}; font-size:12pt")
        label = self._hw_status_labels.get(device)
        if label:
            label.setText(HW_STATUS_TEXT.get(status, "—"))
            label.setStyleSheet(f"color:{color}; font-size:9pt")

    # ── Progress updates ──────────────────────────────────────────────────────
    def _update_progress(self, msg: dict):
        if "percent" in msg:
            self._progress_bar.setValue(int(msg["percent"]))
        if "status" in msg:
            self._status_lbl.setText(msg["status"])
        if "leg" in msg and "total_legs" in msg:
            self._leg_lbl.setText(f"{msg['leg']}/{msg['total_legs']}")
        if "wavelength" in msg:
            self._wl_lbl.setText(f"{msg['wavelength']} nm")
        if "acq" in msg and "total_acq" in msg:
            self._acq_lbl.setText(f"{msg['acq']}/{msg['total_acq']}")
        if "fringe_metric" in msg:
            self._fringe_lbl.setText(f"{msg['fringe_metric']:.3f}")

    # ── Background hardware poller ──────────────────────────────────────────────
    def _mark_user_action(self):
        """Stamp the last-user-action time so the poller backs off briefly and
        the user's GPIB/serial command isn't stuck behind a poll in flight."""
        self._user_action_time = time.monotonic()

    def _background_poller(self):
        """Single daemon thread that reads hardware state and posts updates via
        the signal bridge. Keeps blocking SDK calls off the GUI thread."""
        tick = 0
        self._user_action_time = 0.0
        while not self._stop_background.is_set():
            user_busy = (time.monotonic() - self._user_action_time) < 1.5

            if self.motors:
                for i in (1, 2, 3):
                    try:
                        a = self.motors.getPosition(i)
                        self._post({"type": "paddle_pos", "paddle": i, "value": a})
                    except Exception:
                        pass

            if self.laser and not user_busy:
                slot = tick % 10
                try:
                    if slot == 0:
                        self._post({"type": "laser_wl", "value": self.laser.checkWavelength()})
                    elif slot == 3:
                        self._post({"type": "laser_pw", "value": self.laser.checkPowerAmplitude()})
                    elif slot == 6:
                        self._post({"type": "laser_out", "value": self.laser.isOutputOn()})
                except Exception:
                    pass

            if tick % 8 == 0 and self.switch and not user_busy:
                try:
                    module = self.config.get("hardware", {}).get(
                        "fiber_switch", {}).get("module", 1)
                    pos = self.switch.get_position(module)
                    if pos is not None:
                        self._post({"type": "switch_pos", "value": pos})
                except Exception:
                    pass

            tick += 1
            self._stop_background.wait(0.3)

# -*- coding: utf-8 -*-
"""Polarization tab — Thorlabs MPC320 three paddles (manual + auto-optimize)."""

import threading
import time

from PySide6.QtWidgets import (
    QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ..style import MUTED


class PolarizationTabMixin:
    def _build_polarization_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)

        intro = QLabel("Three motorized paddles squeeze the fiber to tune polarization. "
                       "For holography you want signal and reference arms parallel — max fringes.")
        intro.setObjectName("Small"); lay.addWidget(intro)

        jog = QHBoxLayout()
        jog.addWidget(QLabel("Jog size"))
        self._jog_size_spin = QDoubleSpinBox(); self._jog_size_spin.setRange(0.1, 10.0)
        self._jog_size_spin.setSingleStep(0.5); self._jog_size_spin.setValue(1.0)
        jog.addWidget(self._jog_size_spin); jog.addWidget(QLabel("°")); jog.addStretch(1)
        lay.addLayout(jog)

        self._paddle_cur_lbls: dict = {}
        self._paddle_target_spins: dict = {}

        for i in (1, 2, 3):
            card = QGroupBox(f"Paddle {i}"); ch = QHBoxLayout(card)
            cur = QLabel("—"); cur.setObjectName("BigReadout")
            self._paddle_cur_lbls[i] = cur
            ch.addWidget(cur); ch.addSpacing(20)

            right = QVBoxLayout()
            top = QHBoxLayout()
            top.addWidget(QLabel("Target"))
            sp = QDoubleSpinBox(); sp.setRange(0, 160); sp.setDecimals(1); sp.setValue(0.0)
            self._paddle_target_spins[i] = sp
            sp.editingFinished.connect(lambda p=i: self._move_paddle(p))
            top.addWidget(sp)
            mv = QPushButton("Move To"); mv.setObjectName("Accent")
            mv.clicked.connect(lambda _c=False, p=i: self._move_paddle(p))
            home = QPushButton("Home")
            home.clicked.connect(lambda _c=False, p=i: self._home_paddle(p))
            top.addWidget(mv); top.addWidget(home); top.addStretch(1)
            right.addLayout(top)

            bot = QHBoxLayout()
            jl = QPushButton("«  Jog"); jl.clicked.connect(lambda _c=False, p=i: self._jog_paddle(p, -1))
            jr = QPushButton("Jog  »"); jr.clicked.connect(lambda _c=False, p=i: self._jog_paddle(p, +1))
            bot.addWidget(jl); bot.addWidget(jr); bot.addStretch(1)
            right.addLayout(bot)

            ch.addLayout(right, 1)
            lay.addWidget(card)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet(f"color:{MUTED}")
        lay.addWidget(line)

        ctrl = QHBoxLayout()
        home_all = QPushButton("Home all"); home_all.clicked.connect(self._home_all_paddles)
        self._pol_optimize_btn = QPushButton("Auto-optimize for fringes")
        self._pol_optimize_btn.setObjectName("Accent")
        self._pol_optimize_btn.clicked.connect(self._auto_optimize_polarization)
        ctrl.addWidget(home_all); ctrl.addWidget(self._pol_optimize_btn); ctrl.addStretch(1)
        lay.addLayout(ctrl)

        self._pol_status_lbl = QLabel("Connect motors to enable controls.")
        self._pol_status_lbl.setObjectName("Small")
        lay.addWidget(self._pol_status_lbl)
        lay.addStretch(1)

        self.tabs.addTab(tab, "Polarization")

    def _sync_paddle_targets_from_hw(self):
        """Set spin targets to whatever the motors currently report."""
        if not self.motors or not hasattr(self, "_paddle_target_spins"):
            return
        for i in (1, 2, 3):
            try:
                a = (self.motors.getPosition(i)
                     if hasattr(self.motors, "getPosition")
                     else self.motors.angles[i - 1])
                self._paddle_target_spins[i].setValue(float(a))
            except Exception:
                pass
        self._pol_status_lbl.setText("Ready.")

    def _move_paddle(self, paddle: int):
        if not self.motors:
            self._pol_status_lbl.setText("Motors not connected.")
            return
        target = max(0.0, min(160.0, float(self._paddle_target_spins[paddle].value())))
        threading.Thread(target=self._move_paddle_worker, args=(paddle, target), daemon=True).start()

    def _move_paddle_worker(self, paddle: int, target: float):
        try:
            self.motors.moveMotor(paddle, target)
            self._post({"type": "log", "text": f"Paddle {paddle} → {target:.1f}°", "level": "INFO"})
        except Exception as e:
            self._post({"type": "log", "text": f"Paddle {paddle} move failed: {e}", "level": "WARN"})

    def _home_paddle(self, paddle: int):
        if not self.motors:
            self._pol_status_lbl.setText("Motors not connected.")
            return
        self._paddle_target_spins[paddle].setValue(0.0)
        threading.Thread(target=self._home_paddle_worker, args=(paddle,), daemon=True).start()

    def _home_paddle_worker(self, paddle: int):
        try:
            start = (self.motors.getPosition(paddle)
                     if hasattr(self.motors, "getPosition") else None)
            if hasattr(self.motors, "homeMotor"):
                self.motors.homeMotor(paddle)
            else:
                self.motors.moveMotor(paddle, 0.0)
            # Home is a calibration sweep, not a fast move — wait until the motor
            # is no longer busy before sampling final position (cap 30s).
            time.sleep(0.5)
            deadline = time.time() + 30
            while time.time() < deadline and self.motors.isBusy():
                time.sleep(0.2)
            actual = (self.motors.getPosition(paddle)
                      if hasattr(self.motors, "getPosition") else 0.0)
            ok = abs(actual) < 2.0
            extra = "" if start is None else f"  (from {start:.1f}°)"
            self._post({
                "type": "log",
                "text": f"Paddle {paddle} home → now {actual:.1f}°{extra}"
                        + ("" if ok else "  ⚠ didn't reach 0°"),
                "level": "INFO" if ok else "WARN"})
        except Exception as e:
            self._post({"type": "log", "text": f"Paddle {paddle} home failed: {e}", "level": "WARN"})

    def _jog_paddle(self, paddle: int, direction: int):
        if not self.motors:
            self._pol_status_lbl.setText("Motors not connected.")
            return
        try:
            step = float(self._jog_size_spin.value())
        except (ValueError, TypeError):
            step = 1.0
        # Jog from the actual hardware position if available so repeated clicks
        # compound on the real angle, not a stale spin value.
        try:
            cur = (self.motors.getPosition(paddle)
                   if hasattr(self.motors, "getPosition")
                   else self.motors.angles[paddle - 1])
        except Exception:
            cur = float(self._paddle_target_spins[paddle].value())
        new = max(0.0, min(160.0, cur + direction * step))
        self._paddle_target_spins[paddle].setValue(new)
        self._move_paddle(paddle)

    def _home_all_paddles(self):
        if not self.motors:
            self._pol_status_lbl.setText("Motors not connected.")
            return
        for i in (1, 2, 3):
            self._home_paddle(i)

    def _auto_optimize_polarization(self):
        if not self.motors:
            self._pol_status_lbl.setText("Motors not connected.")
            return
        if not self.camera:
            self._pol_status_lbl.setText("Camera needed for fringe-based optimization.")
            return
        if self.experiment_running:
            self._pol_status_lbl.setText("Stop the experiment first.")
            return
        self._pol_optimize_btn.setEnabled(False)
        self._pol_status_lbl.setText("Sweeping paddles — this can take a minute…")
        threading.Thread(target=self._auto_optimize_worker, daemon=True).start()

    def _auto_optimize_worker(self):
        try:
            from fringe_detection import optimize_polarization_for_fringes
            fd = self.config.get("experiment", {}).get("fringe_detection", {})
            success, metric, angles = optimize_polarization_for_fringes(
                self.camera, self.motors,
                max_attempts=int(fd.get("max_attempts", 30)),
                method=fd.get("check_method", "variance"),
                threshold=float(fd.get("min_visibility", 0.15)))
            mark = "✓" if success else "⚠"
            msg = (f"{mark} Auto-optimize: paddles={[round(a, 1) for a in angles]}, "
                   f"metric={metric:.3f}"
                   + ("" if success else f"  (below threshold {fd.get('min_visibility', 0.15)})"))
            self._post({"type": "log", "text": msg, "level": "OK" if success else "WARN"})
            self._post({"type": "pol_status", "text": msg})
        except Exception as e:
            import traceback
            self._post({"type": "log", "text": f"Auto-optimize failed: {e}", "level": "ERROR"})
            self._post({"type": "log", "text": traceback.format_exc(), "level": "DEBUG"})
            self._post({"type": "pol_status", "text": f"Failed: {e}"})
        finally:
            self._post({"type": "pol_optimize_done"})

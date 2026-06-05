# -*- coding: utf-8 -*-
"""Polarization tab — Thorlabs MPC320 three paddles (manual + auto-optimize)."""

import threading
import time
import tkinter as tk
from tkinter import ttk

from ..theme import MUTED


class PolarizationTabMixin:
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

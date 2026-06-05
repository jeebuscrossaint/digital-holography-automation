# -*- coding: utf-8 -*-
"""Laser tab — HP 8168E tunable laser (wavelength / power / output)."""

import threading
import tkinter as tk
from tkinter import ttk

from ..theme import MUTED


class LaserTabMixin:
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
        self._laser_wl_target_init = False   # seed from real readback on first poll
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
        self._laser_pw_target_init = False   # seed from real readback on first poll
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
        target = float(self._laser_wl_target.get())
        self._laser_wl_cur.set(f"{target:.2f}")
        self._log(f"Laser λ → {target:.2f} nm", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_laser_wavelength_worker,
                         args=(target,), daemon=True).start()

    def _set_laser_wavelength_worker(self, target):
        try:
            self.laser.changeWavelength(target)
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Set λ failed: {e}", "level": "WARN"})

    def _set_laser_power(self):
        if not self.laser:
            self._laser_status_var.set("Laser not connected.")
            return
        uw = float(self._laser_pw_target.get())
        self._laser_pw_cur.set(f"{uw:.0f}")
        self._log(f"Laser P → {uw:.0f} µW", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_laser_power_worker,
                         args=(uw,), daemon=True).start()

    def _set_laser_power_worker(self, uw):
        try:
            self.laser.powerAmplitude(uw, "UW")
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Set P failed: {e}", "level": "WARN"})

    def _set_laser_output(self, on):
        if not self.laser:
            self._laser_status_var.set("Laser not connected.")
            return
        self._laser_out_state.set("ON" if on else "OFF")
        self._log(f"Laser output → {'ON' if on else 'OFF'}", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_laser_output_worker,
                         args=(on,), daemon=True).start()

    def _set_laser_output_worker(self, on):
        try:
            self.laser.outputState(on)
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Output toggle failed: {e}",
                                "level": "WARN"})

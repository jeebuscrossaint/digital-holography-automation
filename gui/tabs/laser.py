# -*- coding: utf-8 -*-
"""Laser tab — HP 8168E tunable laser (wavelength / power / output)."""

import threading

from PySide6.QtWidgets import (
    QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..style import MUTED


class LaserTabMixin:
    def _build_laser_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)

        intro = QLabel("HP 8168E tunable laser. 1475–1575 nm, SCPI over GPIB.")
        intro.setObjectName("Small"); lay.addWidget(intro)

        # Wavelength card
        wl = QGroupBox("Wavelength"); wlh = QHBoxLayout(wl)
        self._laser_wl_cur_lbl = QLabel("—"); self._laser_wl_cur_lbl.setObjectName("BigReadout")
        wlh.addWidget(self._laser_wl_cur_lbl); wlh.addWidget(QLabel("nm")); wlh.addSpacing(16)
        wlh.addWidget(QLabel("Target"))
        self._laser_wl_spin = QDoubleSpinBox(); self._laser_wl_spin.setRange(1475, 1575)
        self._laser_wl_spin.setDecimals(2); self._laser_wl_spin.setValue(1550.0)
        self._laser_wl_target_init = False
        self._laser_wl_spin.editingFinished.connect(self._set_laser_wavelength)
        wlh.addWidget(self._laser_wl_spin); wlh.addWidget(QLabel("nm"))
        wlbtn = QPushButton("Set λ"); wlbtn.setObjectName("Accent")
        wlbtn.clicked.connect(self._set_laser_wavelength); wlh.addWidget(wlbtn)
        wlh.addStretch(1)
        lay.addWidget(wl)

        # Power card
        pw = QGroupBox("Power"); pwh = QHBoxLayout(pw)
        self._laser_pw_cur_lbl = QLabel("—"); self._laser_pw_cur_lbl.setObjectName("BigReadout")
        pwh.addWidget(self._laser_pw_cur_lbl); pwh.addWidget(QLabel("µW")); pwh.addSpacing(16)
        pwh.addWidget(QLabel("Target"))
        self._laser_pw_spin = QDoubleSpinBox(); self._laser_pw_spin.setRange(50, 500)
        self._laser_pw_spin.setDecimals(0); self._laser_pw_spin.setSingleStep(10)
        self._laser_pw_spin.setValue(208)
        self._laser_pw_target_init = False
        self._laser_pw_spin.editingFinished.connect(self._set_laser_power)
        pwh.addWidget(self._laser_pw_spin); pwh.addWidget(QLabel("µW"))
        pwbtn = QPushButton("Set P"); pwbtn.setObjectName("Accent")
        pwbtn.clicked.connect(self._set_laser_power); pwh.addWidget(pwbtn)
        pwh.addStretch(1)
        lay.addWidget(pw)

        # Output card
        out = QGroupBox("Output"); outh = QHBoxLayout(out)
        self._laser_out_lbl = QLabel("—"); self._laser_out_lbl.setObjectName("BigReadout")
        outh.addWidget(self._laser_out_lbl); outh.addSpacing(16)
        on_btn = QPushButton("Turn ON"); on_btn.setObjectName("Accent")
        on_btn.clicked.connect(lambda: self._set_laser_output(True))
        off_btn = QPushButton("Turn OFF")
        off_btn.clicked.connect(lambda: self._set_laser_output(False))
        outh.addWidget(on_btn); outh.addWidget(off_btn); outh.addStretch(1)
        lay.addWidget(out)

        self._laser_status_lbl = QLabel("Connect to enable controls.")
        self._laser_status_lbl.setObjectName("Small")
        lay.addWidget(self._laser_status_lbl)
        lay.addStretch(1)

        self.tabs.addTab(tab, "Laser")

    def _set_laser_wavelength(self):
        if not self.laser:
            self._laser_status_lbl.setText("Laser not connected.")
            return
        target = float(self._laser_wl_spin.value())
        self._laser_wl_cur_lbl.setText(f"{target:.2f}")
        self._log(f"Laser λ → {target:.2f} nm", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_laser_wavelength_worker, args=(target,), daemon=True).start()

    def _set_laser_wavelength_worker(self, target):
        try:
            self.laser.changeWavelength(target)
        except Exception as e:
            self._post({"type": "log", "text": f"Set λ failed: {e}", "level": "WARN"})

    def _set_laser_power(self):
        if not self.laser:
            self._laser_status_lbl.setText("Laser not connected.")
            return
        uw = float(self._laser_pw_spin.value())
        self._laser_pw_cur_lbl.setText(f"{uw:.0f}")
        self._log(f"Laser P → {uw:.0f} µW", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_laser_power_worker, args=(uw,), daemon=True).start()

    def _set_laser_power_worker(self, uw):
        try:
            self.laser.powerAmplitude(uw, "UW")
        except Exception as e:
            self._post({"type": "log", "text": f"Set P failed: {e}", "level": "WARN"})

    def _set_laser_output(self, on):
        if not self.laser:
            self._laser_status_lbl.setText("Laser not connected.")
            return
        self._laser_out_lbl.setText("ON" if on else "OFF")
        self._log(f"Laser output → {'ON' if on else 'OFF'}", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_laser_output_worker, args=(on,), daemon=True).start()

    def _set_laser_output_worker(self, on):
        try:
            self.laser.outputState(on)
        except Exception as e:
            self._post({"type": "log", "text": f"Output toggle failed: {e}", "level": "WARN"})

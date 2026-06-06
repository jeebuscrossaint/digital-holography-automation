# -*- coding: utf-8 -*-
"""Switch tab — Dicon GP700 fiber switch (route input fiber to a lantern leg)."""

import threading

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


class SwitchTabMixin:
    def _build_switch_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)

        intro = QLabel("Dicon GP700 fiber switch. Routes the input fiber to one of "
                       "N output ports (legs of the photonic lantern).")
        intro.setObjectName("Small"); lay.addWidget(intro)

        pos = QGroupBox("Current leg"); ph = QHBoxLayout(pos)
        self._switch_pos_cur_lbl = QLabel("—"); self._switch_pos_cur_lbl.setObjectName("BigReadout")
        ph.addWidget(self._switch_pos_cur_lbl); ph.addSpacing(16)
        ph.addWidget(QLabel("Go to leg"))
        self._switch_pos_spin = QSpinBox(); self._switch_pos_spin.setRange(1, 16)
        self._switch_pos_spin.setValue(1)
        ph.addWidget(self._switch_pos_spin)
        mv = QPushButton("Move"); mv.setObjectName("Accent")
        mv.clicked.connect(lambda: self._switch_to_leg(int(self._switch_pos_spin.value())))
        ph.addWidget(mv); ph.addStretch(1)
        lay.addWidget(pos)

        quick = QGroupBox("Quick select"); qh = QHBoxLayout(quick)
        legs = self.config.get("experiment", {}).get("legs", list(range(1, 8)))
        for leg in legs:
            b = QPushButton(f"Leg {leg}")
            b.clicked.connect(lambda _checked=False, l=leg: self._switch_to_leg(l))
            qh.addWidget(b)
        qh.addStretch(1)
        lay.addWidget(quick)

        self._switch_status_lbl = QLabel("Connect to enable controls.")
        self._switch_status_lbl.setObjectName("Small")
        lay.addWidget(self._switch_status_lbl)
        lay.addStretch(1)

        self.tabs.addTab(tab, "Switch")

    def _switch_to_leg(self, leg: int):
        if not self.switch:
            self._switch_status_lbl.setText("Switch not connected.")
            return
        self._switch_pos_spin.setValue(leg)
        self._switch_pos_cur_lbl.setText(str(leg))
        self._log(f"Switch → leg {leg}", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._switch_to_leg_worker, args=(leg,), daemon=True).start()

    def _switch_to_leg_worker(self, leg: int):
        try:
            module = self.config.get("hardware", {}).get("fiber_switch", {}).get("module", 1)
            self.switch.move_to_position(module, leg)
        except Exception as e:
            self._post({"type": "log",
                        "text": f"Switch move to leg {leg} failed: {e}", "level": "WARN"})

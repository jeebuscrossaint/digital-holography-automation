# -*- coding: utf-8 -*-
"""Run Experiment tab — mode/run controls, progress, live exposure + snapshot,
and the camera preview. The preview *loop* and frame rendering live in
``gui.camera``; this tab builds the controls and the label they target."""

import threading

from PySide6.QtWidgets import (
    QButtonGroup, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from ..camera import PreviewLabel
from ..style import MUTED


class RunTabMixin:
    def _build_run_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)

        # Row 1 — mode selector + run controls
        ctrl = QHBoxLayout()
        mode_lbl = QLabel("Mode"); mode_lbl.setStyleSheet("font-weight:bold")
        ctrl.addWidget(mode_lbl)
        self._mode_group = QButtonGroup(tab)
        self._mode_buttons = {}
        for label, val in (("Collect", "collect"), ("Process", "process"), ("Full Run", "full")):
            rb = QRadioButton(label)
            if val == "full":
                rb.setChecked(True)
            self._mode_group.addButton(rb)
            self._mode_buttons[val] = rb
            ctrl.addWidget(rb)
        ctrl.addStretch(1)
        self._start_btn = QPushButton("Start Experiment"); self._start_btn.setObjectName("Accent")
        self._start_btn.setEnabled(True)   # Process mode works offline; collect/full check hw at click
        self._start_btn.clicked.connect(self._start_experiment)
        self._stop_btn = QPushButton("Stop"); self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_experiment)
        ctrl.addWidget(self._start_btn); ctrl.addWidget(self._stop_btn)
        lay.addLayout(ctrl)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet(f"color:{MUTED}")
        lay.addWidget(line)

        # Row 2 — progress
        sec = QLabel("Progress"); sec.setObjectName("Section"); lay.addWidget(sec)
        self._progress_bar = QProgressBar(); self._progress_bar.setRange(0, 100)
        lay.addWidget(self._progress_bar)
        self._status_lbl = QLabel("Connect hardware to begin")
        lay.addWidget(self._status_lbl)

        # Metric strip
        metrics = QHBoxLayout()
        self._leg_lbl    = QLabel("—")
        self._wl_lbl     = QLabel("—")
        self._acq_lbl    = QLabel("0 / 0")
        self._fringe_lbl = QLabel("—")
        for title, w in (("LEG", self._leg_lbl), ("WAVELENGTH", self._wl_lbl),
                         ("IMAGES", self._acq_lbl), ("FRINGE", self._fringe_lbl)):
            cell = QVBoxLayout()
            cap = QLabel(title); cap.setObjectName("Small")
            w.setObjectName("Metric")
            cell.addWidget(cap); cell.addWidget(w)
            metrics.addLayout(cell); metrics.addSpacing(28)
        metrics.addStretch(1)
        lay.addLayout(metrics)

        # Exposure control (live) — raise to brighten / drive saturation, lower
        # to avoid clipping. The configured value is applied at connect.
        expf = QHBoxLayout()
        elbl = QLabel("Exposure"); elbl.setObjectName("Muted"); expf.addWidget(elbl)
        self._cam_exp_spin = QDoubleSpinBox()
        self._cam_exp_spin.setRange(1, 262143); self._cam_exp_spin.setDecimals(0)
        self._cam_exp_spin.setSingleStep(100)
        self._cam_exp_spin.setValue(float(self.config.get("hardware", {})
                                          .get("camera", {}).get("exposure_time", 500)))
        expf.addWidget(self._cam_exp_spin)
        expf.addWidget(QLabel("µs"))
        set_btn = QPushButton("Set"); set_btn.setObjectName("Accent")
        set_btn.clicked.connect(self._set_exposure); expf.addWidget(set_btn)
        snap_btn = QPushButton("📷 Save snapshot")
        snap_btn.clicked.connect(self._save_snapshot); expf.addWidget(snap_btn)
        hint = QLabel("↑ brighten / saturate   ↓ avoid clipping"); hint.setObjectName("Small")
        expf.addWidget(hint); expf.addStretch(1)
        lay.addLayout(expf)

        # Camera preview
        pv = QLabel("Camera Preview"); pv.setObjectName("Section"); lay.addWidget(pv)
        self._preview_lbl = PreviewLabel()
        self._last_frame = None
        lay.addWidget(self._preview_lbl, 1)

        self.tabs.addTab(tab, "Run Experiment")

    def _selected_mode(self) -> str:
        for val, rb in self._mode_buttons.items():
            if rb.isChecked():
                return val
        return "full"

    def _set_exposure(self):
        if not self.camera:
            self._log("Camera not connected.", "WARN")
            return
        us = float(self._cam_exp_spin.value())
        self._log(f"Camera exposure → {us:.0f} µs", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_exposure_worker, args=(us,), daemon=True).start()

    def _set_exposure_worker(self, us):
        try:
            actual = self.camera.setExposure(us)
            self._post({"type": "log", "text": f"  Exposure now {actual:.0f} µs", "level": "OK"})
        except Exception as e:
            self._post({"type": "log", "text": f"Set exposure failed: {e}", "level": "WARN"})

    def _save_snapshot(self):
        """Save the current camera frame as a hologram for analysis — raw .npy
        (16-bit) + .png (preview) + .yaml (metadata). Works without the switch."""
        import numpy as np
        frame = self._last_frame
        if frame is None:
            self._log("No frame to save — connect the camera and wait for preview.", "WARN")
            return
        threading.Thread(target=self._save_snapshot_worker,
                         args=(np.asarray(frame),), daemon=True).start()

    def _save_snapshot_worker(self, arr):
        import os
        import numpy as np
        import yaml
        from datetime import datetime
        try:
            out = self.config.get("data", {}).get("output_dir", "./holography_data")
            os.makedirs(out, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = os.path.join(out, f"snapshot_{stamp}")
            np.save(base + ".npy", arr)                       # raw 16-bit for analysis

            try:
                from PIL import Image
                a = arr.astype(float)
                mn, mx = a.min(), a.max()
                disp = (((a - mn) / (mx - mn)) * 255).astype(np.uint8) \
                    if mx > mn else np.zeros_like(a, np.uint8)
                Image.fromarray(disp, mode="L").save(base + ".png")
            except Exception:
                pass

            meta = {"timestamp": datetime.now().isoformat(),
                    "max_value": int(arr.max()), "mean": float(arr.mean())}
            try:
                from holo.fringe_detection import (calculate_sideband_energy, check_saturation)
                meta["sideband_metric"] = float(calculate_sideband_energy(arr))
                sat = check_saturation(arr)
                meta["saturated"] = bool(sat["saturated"])
                meta["fill_fraction"] = float(sat["fill_fraction"])
            except Exception:
                pass
            try:
                meta["target_wavelength_nm"] = float(self._laser_wl_spin.value())
            except Exception:
                pass
            try:
                meta["exposure_us"] = float(self._cam_exp_spin.value())
            except Exception:
                pass
            with open(base + ".yaml", "w") as f:
                yaml.dump(meta, f)

            sb = meta.get("sideband_metric")
            tail = f"  (sideband={sb:.0f})" if sb is not None else ""
            self._post({"type": "log",
                        "text": f"📷 Saved {os.path.basename(base)}.npy (+png +yaml){tail}",
                        "level": "OK"})
        except Exception as e:
            self._post({"type": "log", "text": f"Snapshot save failed: {e}", "level": "WARN"})

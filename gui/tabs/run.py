# -*- coding: utf-8 -*-
"""Run Experiment tab — mode/run controls, progress, live exposure + snapshot,
and the camera preview canvas. The preview *loop* and frame rendering live in
``gui.camera``; this tab builds the controls and the canvas they target."""

import threading
import tkinter as tk
from tkinter import ttk

from ..theme import MUTED


class RunTabMixin:
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

        # Exposure control (live) — raise to brighten / drive saturation,
        # lower to avoid clipping. The configured value is applied at connect.
        expf = ttk.Frame(tab)
        expf.pack(fill="x", pady=(2, 6))
        ttk.Label(expf, text="Exposure", foreground=MUTED).pack(side="left", padx=(0, 6))
        self._cam_exp_target = tk.DoubleVar(
            value=float(self.config.get("hardware", {})
                        .get("camera", {}).get("exposure_time", 500)))
        sp_exp = ttk.Spinbox(expf, from_=1, to=262143, increment=100,
                             textvariable=self._cam_exp_target, width=10, format="%.0f")
        sp_exp.pack(side="left", padx=2)
        sp_exp.bind("<Return>", lambda _e: self._set_exposure())
        ttk.Label(expf, text="µs", foreground=MUTED).pack(side="left", padx=(2, 6))
        ttk.Button(expf, text="Set", style="Accent.TButton",
                   command=self._set_exposure).pack(side="left", padx=2)
        ttk.Button(expf, text="📷 Save snapshot",
                   command=self._save_snapshot).pack(side="left", padx=(16, 2))
        ttk.Label(expf, text="↑ brighten / saturate   ↓ avoid clipping",
                  foreground=MUTED, font=self._font_small).pack(side="left", padx=(10, 0))

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

    def _set_exposure(self):
        if not self.camera:
            self._log("Camera not connected.", "WARN")
            return
        us = float(self._cam_exp_target.get())
        self._log(f"Camera exposure → {us:.0f} µs", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._set_exposure_worker,
                         args=(us,), daemon=True).start()

    def _set_exposure_worker(self, us):
        try:
            actual = self.camera.setExposure(us)
            self.msg_queue.put({"type": "log",
                                "text": f"  Exposure now {actual:.0f} µs",
                                "level": "OK"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Set exposure failed: {e}", "level": "WARN"})

    def _save_snapshot(self):
        """Save the current camera frame as a hologram for analysis — raw .npy
        (16-bit, for processing) + .png (preview) + .yaml (metadata). Works
        without the switch, so it's the quick way to hand the PI some data."""
        import numpy as np
        frame = self._last_frame
        if frame is None:
            self._log("No frame to save — connect the camera and wait for preview.",
                      "WARN")
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

            # 8-bit PNG preview for quick viewing / sharing
            try:
                from PIL import Image
                a = arr.astype(float)
                mn, mx = a.min(), a.max()
                disp = (((a - mn) / (mx - mn)) * 255).astype(np.uint8) \
                    if mx > mn else np.zeros_like(a, np.uint8)
                Image.fromarray(disp, mode="L").save(base + ".png")
            except Exception:
                pass

            # metadata: conditions + a fringe-quality / saturation read
            meta = {"timestamp": datetime.now().isoformat(),
                    "max_value": int(arr.max()), "mean": float(arr.mean())}
            try:
                from fringe_detection import (calculate_sideband_energy,
                                              check_saturation)
                meta["sideband_metric"] = float(calculate_sideband_energy(arr))
                sat = check_saturation(arr)
                meta["saturated"] = bool(sat["saturated"])
                meta["fill_fraction"] = float(sat["fill_fraction"])
            except Exception:
                pass
            for key, var in (("target_wavelength_nm", "_laser_wl_target"),
                             ("exposure_us", "_cam_exp_target")):
                try:
                    meta[key] = float(getattr(self, var).get())
                except Exception:
                    pass
            with open(base + ".yaml", "w") as f:
                yaml.dump(meta, f)

            sb = meta.get("sideband_metric")
            tail = f"  (sideband={sb:.0f})" if sb is not None else ""
            self.msg_queue.put({"type": "log",
                                "text": f"📷 Saved {os.path.basename(base)}.npy "
                                        f"(+png +yaml){tail}", "level": "OK"})
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Snapshot save failed: {e}", "level": "WARN"})

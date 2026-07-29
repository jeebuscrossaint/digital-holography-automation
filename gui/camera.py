# -*- coding: utf-8 -*-
"""Live camera preview — the background grab loop, live saturation warnings,
and rendering frames onto the Run tab's preview label.

PreviewLabel rescales a *cached* pixmap on resize (a cheap Qt scale), so
maximizing / dragging the window stays smooth — the source frame is not
re-rendered on every resize event."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel

from .style import MUTED


class PreviewLabel(QLabel):
    """Shows a camera frame, scaled to fit while keeping aspect ratio. Holds the
    source pixmap so resizing just rescales it (no source re-render)."""
    def __init__(self):
        super().__init__("No signal")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(360, 280)
        self.setStyleSheet(f"background:#0a0a0a; border:1px solid #3a3a3a; color:{MUTED}")
        self._src: QPixmap | None = None

    def set_frame(self, pixmap: QPixmap):
        self._src = pixmap
        self._rescale()

    def resizeEvent(self, event):
        self._rescale()
        super().resizeEvent(event)

    def _rescale(self):
        if self._src is None:
            return
        self.setPixmap(self._src.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class CameraMixin:
    def _camera_preview_loop(self):
        """Continuous live preview — grab a frame ~10× per second whenever the
        camera is connected. Surfaces the first frame's stats, OR a warning if
        the SDK keeps returning no frames (so the user can see the difference
        between 'no light' and 'no frames at all')."""
        import numpy as np
        from holo.fringe_detection import check_saturation
        val = self.config.get("experiment", {}).get("validation", {})
        sat_level    = float(val.get("saturation_level", 65535))
        sat_frac_max = float(val.get("max_saturated_fraction", 0.001))
        null_streak = 0
        was_saturated = False   # log only on transition, so we don't spam
        while not self._stop_background.is_set():
            cam = self.camera
            if cam is not None and not self.experiment_running:
                try:
                    frame = cam.getFrame()
                    if frame is not None:
                        null_streak = 0
                        if not self._cam_first_frame_logged:
                            arr = np.asarray(frame)
                            self._post({
                                "type": "log",
                                "text": (f"Camera frame: shape={arr.shape}, "
                                         f"dtype={arr.dtype}, "
                                         f"min={int(arr.min())}, max={int(arr.max())}, "
                                         f"mean={float(arr.mean()):.1f}"),
                                "level": "DEBUG"})
                            self._cam_first_frame_logged = True
                        sat = check_saturation(frame, sat_level=sat_level,
                                               sat_fraction_max=sat_frac_max)
                        if sat["saturated"] and not was_saturated:
                            self._post({
                                "type": "log",
                                "text": (f"⚠ Camera SATURATING — "
                                         f"{sat['fraction']*100:.2f}% of pixels "
                                         f"clipped (max {sat['max_value']}/"
                                         f"{int(sat_level)}). Reduce exposure or "
                                         f"laser power; clipped fringes = invalid "
                                         f"holograms."),
                                "level": "WARN"})
                        elif was_saturated and not sat["saturated"]:
                            self._post({"type": "log",
                                        "text": "✓ Saturation cleared.", "level": "OK"})
                        was_saturated = sat["saturated"]
                        self._post({"type": "frame", "data": frame})
                    else:
                        null_streak += 1
                        if null_streak == 5 and not self._cam_first_frame_logged:
                            self._post({
                                "type": "log",
                                "text": ("Camera connected but no frames are "
                                         "arriving. Almost always: (1) Windows "
                                         "Firewall is blocking inbound GigE "
                                         "stream packets for this app — run "
                                         "tools/setup_lab_machine.ps1 as admin; "
                                         "or (2) Xeneth is open and holding the "
                                         "camera — close it. NOT a light issue."),
                                "level": "WARN"})
                            self._cam_first_frame_logged = True
                except Exception as e:
                    if not self._cam_first_frame_logged:
                        self._post({"type": "log",
                                    "text": f"Camera getFrame failed: {e}",
                                    "level": "WARN"})
                        self._cam_first_frame_logged = True
            else:
                if cam is None:
                    self._cam_first_frame_logged = False
                    null_streak = 0
            self._stop_background.wait(0.1)

    def _show_frame(self, data):
        """Render a raw camera frame onto the preview label (GUI thread)."""
        import numpy as np
        self._last_frame = data
        try:
            arr = np.asarray(data)
            if arr.size == 0:
                return
            # Normalize to 0–255 uint8. Stretch using mean ± 3·std rather than
            # absolute min/max — Bobcat 320 frames are 14-bit; raw min/max
            # stretch makes sensor noise look like clouds and signal look flat.
            f = arr.astype(np.float32)
            mu, sd = float(f.mean()), float(f.std())
            if sd < 1e-6:
                disp = np.full(f.shape, 128, dtype=np.uint8)
            else:
                lo, hi = mu - 3 * sd, mu + 3 * sd
                disp = np.clip((f - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)

            disp = np.ascontiguousarray(disp)
            h, w = disp.shape
            img = QImage(bytes(disp.data), w, h, w, QImage.Format_Grayscale8)
            self._preview_lbl.set_frame(QPixmap.fromImage(img))
        except Exception:
            pass

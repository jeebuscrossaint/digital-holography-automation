# -*- coding: utf-8 -*-
"""Live camera preview — the background grab loop, live saturation warnings,
and rendering frames onto the Run tab's canvas."""


class CameraMixin:
    def _camera_preview_loop(self):
        """Continuous live preview — grab a frame ~10× per second whenever
        the camera is connected. Surfaces the first frame's stats, OR a
        warning if the SDK keeps returning no frames (so the user can
        see the difference between 'no light' and 'no frames at all')."""
        import numpy as np
        from fringe_detection import check_saturation
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
                            self.msg_queue.put({
                                "type": "log",
                                "text": (f"Camera frame: shape={arr.shape}, "
                                         f"dtype={arr.dtype}, "
                                         f"min={int(arr.min())}, max={int(arr.max())}, "
                                         f"mean={float(arr.mean()):.1f}"),
                                "level": "DEBUG",
                            })
                            self._cam_first_frame_logged = True
                        # Live saturation warning — lets you back off exposure /
                        # power while aligning, before clipping ruins a run.
                        sat = check_saturation(frame, sat_level=sat_level,
                                               sat_fraction_max=sat_frac_max)
                        if sat["saturated"] and not was_saturated:
                            self.msg_queue.put({
                                "type": "log",
                                "text": (f"⚠ Camera SATURATING — "
                                         f"{sat['fraction']*100:.2f}% of pixels "
                                         f"clipped (max {sat['max_value']}/"
                                         f"{int(sat_level)}). Reduce exposure or "
                                         f"laser power; clipped fringes = invalid "
                                         f"holograms."),
                                "level": "WARN"})
                        elif was_saturated and not sat["saturated"]:
                            self.msg_queue.put({
                                "type": "log",
                                "text": "✓ Saturation cleared.", "level": "OK"})
                        was_saturated = sat["saturated"]
                        self.msg_queue.put({"type": "frame", "data": frame})
                    else:
                        null_streak += 1
                        if null_streak == 5 and not self._cam_first_frame_logged:
                            self.msg_queue.put({
                                "type": "log",
                                "text": ("Camera connected but no frames are "
                                         "arriving. Almost always: (1) Windows "
                                         "Firewall is blocking inbound GigE "
                                         "stream packets for this Python — run "
                                         "tools/setup_lab_machine.ps1 as admin; "
                                         "or (2) Xeneth is open and holding the "
                                         "camera — close it. NOT a light issue."),
                                "level": "WARN",
                            })
                            self._cam_first_frame_logged = True
                except Exception as e:
                    if not self._cam_first_frame_logged:
                        self.msg_queue.put({
                            "type": "log",
                            "text": f"Camera getFrame failed: {e}",
                            "level": "WARN",
                        })
                        self._cam_first_frame_logged = True
            else:
                if cam is None:
                    self._cam_first_frame_logged = False
                    null_streak = 0
            self._stop_background.wait(0.1)

    def _redraw_frame(self):
        if self._last_frame is not None:
            self._show_frame(self._last_frame)

    def _show_frame(self, data):
        self._last_frame = data
        try:
            from PIL import Image, ImageTk
            import numpy as np

            arr = np.asarray(data)
            # Normalize to 0–255 uint8 for display. Stretch using mean ±
            # 3·std rather than absolute min/max — Bobcat 320 frames are
            # 14-bit; raw min/max stretch makes a uniform sensor noise
            # field look like vague clouds and a real signal look flat.
            if arr.size == 0:
                return
            f = arr.astype(np.float32)
            mu, sd = float(f.mean()), float(f.std())
            if sd < 1e-6:
                # Truly flat frame — show as mid-gray so it's obvious vs.
                # a stretched bright frame
                arr = np.full(f.shape, 128, dtype=np.uint8)
            else:
                lo, hi = mu - 3 * sd, mu + 3 * sd
                arr = np.clip((f - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)

            cw = max(self._canvas.winfo_width(),  10)
            ch = max(self._canvas.winfo_height(), 10)

            # Fit image while preserving aspect ratio
            ih, iw = arr.shape
            scale = min(cw / iw, ch / ih)
            tw, th = max(int(iw * scale), 1), max(int(ih * scale), 1)

            img   = Image.fromarray(arr, mode="L").resize((tw, th), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._canvas.delete("nosignal")
            self._canvas.delete("frame")
            self._canvas.create_image(cw // 2, ch // 2, anchor="center",
                                      image=photo, tags="frame")
            self._canvas_photo = photo  # prevent GC
        except Exception:
            pass

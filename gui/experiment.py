# -*- coding: utf-8 -*-
"""The experiment run: collection (sweep legs × wavelengths, optimize
polarization, validate saturation, save) and processing (reconstruct each
hologram). This is the single source-of-truth acquisition loop for the app."""

import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .runtime import CONFIG_FILE


def format_capture_name(fmt: str, leg, wl) -> str:
    """Build a save filename that tolerates fractional wavelengths.

    Whole-number wavelengths use the configured format verbatim (e.g.
    ``leg01-wavelength1525.npy`` — unchanged/backward compatible). A fractional
    wavelength would crash the default ``{wavelength:04d}`` integer code, so we
    fall back to a dot-free tag (``leg01-wavelength1525p1.npy``) — the 'p' keeps
    the file extension clean. The true wavelength is always stored in the .yaml
    metadata, so the filename is just a label."""
    leg = int(leg)
    try:
        return fmt.format(leg=leg,
                          wavelength=int(wl) if float(wl).is_integer() else wl)
    except (ValueError, KeyError):
        import re
        safe = re.sub(r"\{wavelength[^}]*\}", "{wavelength}", fmt)
        tag = f"{float(wl):.4f}".rstrip("0").rstrip(".").replace(".", "p")
        return safe.format(leg=leg, wavelength=tag)


def read_paddle_angles(motors):
    """Actual paddle positions read from the hardware. Deliberately not
    motors.angles — that is the last *commanded* angle, which is stale
    ([0,0,0]) if the app hasn't moved the paddles this session, and it would
    be recorded into the capture metadata as if it were measured."""
    if motors is None:
        return [0.0, 0.0, 0.0]
    out = []
    for i in (1, 2, 3):
        try:
            out.append(round(float(motors.getPosition(i)), 2))
        except Exception:
            try:
                out.append(round(float(motors.angles[i - 1]), 2))
            except Exception:
                out.append(0.0)
    return out


def save_preview_png(frame, path):
    """Save a viewable 8-bit PNG of a raw frame (mean ± 3σ contrast stretch)."""
    try:
        import numpy as np
        from PIL import Image
        a = np.asarray(frame).astype(np.float32)
        mu, sd = float(a.mean()), float(a.std())
        if sd < 1e-6:
            disp = np.full(a.shape, 128, np.uint8)
        else:
            lo, hi = mu - 3 * sd, mu + 3 * sd
            disp = np.clip((a - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
        Image.fromarray(disp, "L").save(str(path))
    except Exception:
        pass


class ExperimentMixin:
    def _start_experiment(self):
        mode = self._selected_mode()
        # Collection needs hardware; processing just reads existing .npy files,
        # so allow it offline (e.g. reprocessing a dataset on a laptop).
        if mode in ("collect", "full") and not self.hardware_connected:
            QMessageBox.warning(self, "Not Connected",
                                "Connect hardware first (collection needs the camera/laser). "
                                "To reprocess existing data without hardware, use Process mode.")
            return
        self.experiment_running = True
        self.stop_event.clear()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._status_lbl.setText("Starting…")
        self._log(f"Experiment started (mode: {mode})", "INFO")
        threading.Thread(target=self._experiment_worker,
                         args=(mode,), daemon=True).start()

    def _stop_experiment(self):
        self.stop_event.set()
        self._stop_btn.setEnabled(False)
        self._log("Stop requested — finishing current acquisition…", "WARN")

    def _experiment_worker(self, mode: str):
        cb = self._post
        try:
            if mode in ("collect", "full"):
                self._run_collection(cb)
            if mode in ("process", "full") and not self.stop_event.is_set():
                self._run_processing(cb)

            if self.stop_event.is_set():
                cb({"type": "log", "text": "Experiment stopped by user.", "level": "WARN"})
                cb({"type": "done", "event": "experiment", "success": False})
            else:
                cb({"type": "log", "text": "✓ Experiment complete!", "level": "OK"})
                cb({"type": "done", "event": "experiment", "success": True})
        except Exception as e:
            import traceback
            cb({"type": "log", "text": f"Experiment error: {e}", "level": "ERROR"})
            cb({"type": "log", "text": traceback.format_exc(), "level": "DEBUG"})
            cb({"type": "done", "event": "experiment", "success": False})

    # ── Collection ────────────────────────────────────────────────────────────
    def _run_collection(self, cb):
        import numpy as np
        import yaml
        from holo.fringe_detection import (check_fringes_visible,
                                       optimize_polarization_for_fringes,
                                       check_saturation)

        cfg    = self.config
        val    = cfg.get("experiment", {}).get("validation", {})
        sat_level    = float(val.get("saturation_level", 65535))
        sat_frac_max = float(val.get("max_saturated_fraction", 0.001))
        legs   = cfg["experiment"]["legs"]
        wls    = cfg["experiment"]["wavelengths"]
        waits  = cfg["experiment"]["wait_times"]
        fdet   = cfg["experiment"]["fringe_detection"]
        pol_cfg    = cfg["experiment"].get("polarization", {})
        motors_cfg = cfg["hardware"].get("polarization_motors", {})
        fmt    = cfg["data"]["filename_format"]
        out    = Path(cfg["data"]["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        module = cfg["hardware"]["fiber_switch"]["module"]
        total  = len(legs) * len(wls)
        n      = 0

        if not self.camera:
            cb({"type": "log",
                "text": "Camera not connected — cannot collect.", "level": "ERROR"})
            return
        if not self.switch and len(legs) > 1:
            cb({"type": "log",
                "text": f"Switch not connected — all {len(legs)} legs will be saved at the current optical path.",
                "level": "WARN"})
        if not self.laser and len(wls) > 1:
            cb({"type": "log",
                "text": f"Laser not connected — all {len(wls)} wavelengths will be saved at the current λ.",
                "level": "WARN"})

        # Auto-enable the laser before a (possibly walk-away) run, and CONFIRM it
        # took — guards against the "booted up, hit Full, came back to a dead
        # dataset because the laser was off all day" trap.
        if self.laser:
            try:
                self.laser.outputState(True)
                time.sleep(0.3)
                on = "1" in str(self.laser.isOutputOn())
                cb({"type": "log",
                    "text": ("Laser output ON (auto-enabled for the run)" if on else
                             "⚠ Laser would NOT confirm ON — check it before walking away, "
                             "this run may capture dark frames"),
                    "level": "OK" if on else "WARN"})
            except Exception as e:
                cb({"type": "log",
                    "text": f"⚠ Couldn't enable laser output: {e} — check the laser",
                    "level": "WARN"})

        cb({"type": "log",
            "text": f"Collection: {len(legs)} legs × {len(wls)} wavelengths = {total} images",
            "level": "INFO"})

        for li, leg in enumerate(legs):
            if self.stop_event.is_set():
                break

            cb({"type": "log", "text": f"── Leg {leg} ──", "level": "INFO"})
            cb({"type": "progress", "leg": li + 1, "total_legs": len(legs),
                "status": f"Switching to leg {leg}…"})

            if self.switch:
                self.switch.move_to_position(module, leg)
            time.sleep(waits["after_leg_switch"])

            for _wi, wl in enumerate(wls):
                if self.stop_event.is_set():
                    break

                n += 1
                cb({"type": "progress",
                    "percent": (n - 1) / total * 100,
                    "leg": li + 1, "total_legs": len(legs),
                    "wavelength": wl,
                    "acq": n, "total_acq": total,
                    "status": f"Leg {leg}, λ={wl} nm — setting wavelength…"})

                if self.laser:
                    self.laser.changeWavelength(wl)
                time.sleep(waits["after_wavelength_change"])

                frame = self.camera.getFrame() if self.camera else None

                if frame is not None:
                    cb({"type": "frame", "data": frame})

                    if fdet["enabled"]:
                        method    = fdet["check_method"]
                        threshold = fdet["min_visibility"]
                        ok, metric = check_fringes_visible(frame, method, threshold)
                        cb({"type": "progress", "fringe_metric": metric,
                            "status": f"Leg {leg}, λ={wl} nm — fringe: {metric:.3f}"})

                        if not ok and self.motors:
                            cb({"type": "log",
                                "text": f"  Low fringes ({metric:.3f}) — optimizing polarization…",
                                "level": "WARN"})
                            success, best, _ = optimize_polarization_for_fringes(
                                self.camera, self.motors,
                                max_attempts=fdet["max_attempts"],
                                method=method, threshold=threshold,
                                angle_step=float(pol_cfg.get("angle_step", 20)),
                                max_travel=float(motors_cfg.get("max_travel", 160)))
                            if success:
                                cb({"type": "log",
                                    "text": f"  ✓ Polarization optimized (metric={best:.3f})",
                                    "level": "OK"})
                                time.sleep(waits["after_polarization_adjust"])
                                frame = self.camera.getFrame()
                                if frame is not None:
                                    cb({"type": "frame", "data": frame})
                            else:
                                cb({"type": "log",
                                    "text": f"  ⚠ Could not optimize (best={best:.3f}) — saving anyway",
                                    "level": "WARN"})
                        elif ok:
                            cb({"type": "log",
                                "text": f"  ✓ Fringes OK ({metric:.3f})", "level": "OK"})
                else:
                    cb({"type": "log",
                        "text": "  ✗ Frame capture failed — skipping", "level": "WARN"})

                if frame is not None:
                    # Saturation/clipping check — a clipped fringe is no longer
                    # a clean sinusoid, so its FFT sideband (and the recovered
                    # amplitude/phase) are corrupted. Flag it; still save so the
                    # raw data isn't lost, but mark it invalid in metadata.
                    sat = check_saturation(frame, sat_level=sat_level,
                                           sat_fraction_max=sat_frac_max)
                    if sat["saturated"]:
                        cb({"type": "log",
                            "text": (f"  ⚠ SATURATED — {sat['fraction']*100:.2f}% "
                                     f"of pixels clipped (max {sat['max_value']}/"
                                     f"{int(sat_level)}). Data INVALID — reduce "
                                     f"exposure or laser power."),
                            "level": "WARN"})

                    fname = format_capture_name(fmt, leg, wl)
                    fpath = out / fname
                    np.save(fpath, frame)
                    save_preview_png(frame, fpath.with_suffix(".png"))   # viewable pic

                    if cfg["data"]["save_metadata"]:
                        angles = read_paddle_angles(self.motors)   # actual positions
                        meta = {"leg": leg, "wavelength_nm": wl,
                                "timestamp": datetime.now().isoformat(),
                                "polarizer_angles_deg": angles,
                                "motor_angles": angles,            # back-compat key
                                "saturated": bool(sat["saturated"]),
                                "saturated_fraction": float(sat["fraction"]),
                                "max_value": int(sat["max_value"]),
                                "fill_fraction": float(sat["fill_fraction"])}
                        with open(fpath.with_suffix(".yaml"), "w") as f:
                            yaml.dump(meta, f)

                    tag = "WARN" if sat["saturated"] else "OK"
                    flag = "  ⚠ invalid(saturated)" if sat["saturated"] else ""
                    cb({"type": "log", "text": f"  💾 {fname}{flag}", "level": tag})

                cb({"type": "progress",
                    "percent": n / total * 100,
                    "acq": n, "total_acq": total,
                    "status": f"Completed {n}/{total} images"})

        cb({"type": "log",
            "text": f"Collection done — {n} images saved to {out}", "level": "OK"})

    # ── Processing ────────────────────────────────────────────────────────────
    def _run_processing(self, cb):
        import re
        import yaml

        from holo import pipeline

        cb({"type": "log",  "text": "Starting data processing…", "level": "INFO"})
        cb({"type": "progress", "status": "Loading processor…", "percent": 0})

        def log(text, level="INFO"):
            cb({"type": "log", "text": text, "level": level})

        try:
            from holo.data_processing import HolographyDataProcessor
            proc = HolographyDataProcessor(config_file=CONFIG_FILE)
        except Exception as e:
            log(f"Processor init failed: {e}", "ERROR")
            return

        files = sorted(Path(proc.data_dir).glob("leg*.npy"))
        if not files:
            log("No hologram files found — run collection first", "WARN")
            return
        log(f"Found {len(files)} holograms", "INFO")

        def leg_wl_of(name):
            """Leg and wavelength encoded in a capture filename. A fractional
            wavelength is written 1547p3 (not 1547.3), so the token is digits +
            optional 'p' + digits — a literal dot would swallow the extension."""
            lm = re.search(r"leg(\d+)", name)
            wm = re.search(r"wavelength(\d+(?:p\d+)?)", name)
            return (int(lm.group(1)) if lm else None,
                    float(wm.group(1).replace("p", ".")) if wm else None)

        records = []
        for f in files:
            leg, wl = leg_wl_of(f.name)
            meta = f.with_suffix(".yaml")
            if meta.exists():
                try:
                    wl = yaml.safe_load(meta.read_text()).get("wavelength_nm", wl)
                except Exception:
                    pass
            records.append({"path": f, "label": f.stem, "leg": leg,
                            "wl": float(wl if wl is not None else 1550)})

        # Reference library, indexed by wavelength so a fine (e.g. 0.1 nm)
        # library can serve a sweep at any step via nearest-λ match.
        pcfg = self.config.get("processing", {})
        bg_dir = pcfg.get("background_dir")
        ref_index = {}
        if pcfg.get("subtract_background") and bg_dir and Path(bg_dir).exists():
            for rp in Path(bg_dir).glob("*.npy"):
                _, w = leg_wl_of(rp.name)
                if w is not None:
                    ref_index[w] = rp
            log(f"Background subtraction ON — {len(ref_index)} reference "
                f"wavelengths in {bg_dir} "
                f"(modifier {pcfg.get('background_modifier', 1.0)}, nearest-λ match)",
                "INFO")

        done = [0]

        def progress_log(text, level="INFO"):
            log(text, level)
            if text.startswith("["):        # one per frame
                done[0] += 1
                cb({"type": "progress",
                    "percent": done[0] / len(records) * 100,
                    "status": f"Processing {done[0]}/{len(records)}",
                    "acq": done[0], "total_acq": len(records)})

        rows = pipeline.process_records(
            proc, records, config=self.config, log=progress_log,
            ref_index=ref_index, save=True, show=False,
            should_stop=self.stop_event.is_set)

        pipeline.write_summary(proc.results_dir, rows, log=log)

        cb({"type": "progress", "percent": 100, "status": "Processing complete"})
        log("Data processing complete", "OK")

    # ── Done handler (GUI thread) ───────────────────────────────────────────────
    def _on_done(self, event: str, success: bool):
        self.experiment_running = False
        self._stop_btn.setEnabled(False)

        if event == "connect":
            ok    = getattr(self, "_connected_names", [])
            all_4 = ("Laser", "Camera", "Switch", "Motors")
            off   = [d for d in all_4 if d not in ok]
            connected_lower = {d.lower() for d in ok}

            # Keep connect controls usable so more devices can be added; a
            # device's own button greys out once it's connected. Disconnect is
            # available whenever anything is connected.
            self._connect_btn.setEnabled(len(ok) < 4)
            for name, b in getattr(self, "_hw_connect_btns", {}).items():
                b.setEnabled(name not in connected_lower)
            self._disconnect_btn.setEnabled(len(ok) > 0)

            if len(ok) == 4:
                self._status_lbl.setText("All 4 devices connected — ready to run")
                self._log("All hardware connected. Press ▶ START when ready.", "OK")
            elif len(ok) == 0:
                self._status_lbl.setText("No devices connected — check cables & config")
                self._log("No devices connected. Check cables, COM ports, and GPIB address.", "ERROR")
            else:
                summary = f"{len(ok)}/4 connected: {', '.join(ok)}"
                missing = f"Offline: {', '.join(off)}"
                self._status_lbl.setText(f"{summary} — {missing}")
                self._log(f"{summary}", "OK")
                self._log(f"{missing} — plug in and click Connect to retry", "WARN")

            self._start_btn.setEnabled(True)   # Process is always available; collect/full check hw at click
            if "Motors" in ok:
                self._sync_paddle_targets_from_hw()
        elif event == "experiment":
            self._start_btn.setEnabled(True)
            if success:
                self._progress_bar.setValue(100)
                self._status_lbl.setText("Experiment complete!")
                self._refresh_results()
                QMessageBox.information(self, "Done",
                    "Experiment completed successfully!\nCheck the Results tab.")
            else:
                self._status_lbl.setText("Stopped / error — see log")

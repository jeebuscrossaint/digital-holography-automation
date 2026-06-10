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


class ExperimentMixin:
    def _start_experiment(self):
        if not self.hardware_connected:
            QMessageBox.warning(self, "Not Connected", "Connect hardware first.")
            return
        mode = self._selected_mode()
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
        from fringe_detection import (check_fringes_visible,
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
                                method=method, threshold=threshold)
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

                    if cfg["data"]["save_metadata"]:
                        try:
                            angles = list(self.motors.angles)
                        except Exception:
                            angles = [0, 0, 0]
                        meta = {"leg": leg, "wavelength_nm": wl,
                                "timestamp": datetime.now().isoformat(),
                                "motor_angles": angles,
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
        import yaml

        cb({"type": "log",  "text": "Starting data processing…", "level": "INFO"})
        cb({"type": "progress", "status": "Loading processor…", "percent": 0})

        try:
            from data_processing import HolographyDataProcessor
            proc = HolographyDataProcessor(config_file=CONFIG_FILE)
        except Exception as e:
            cb({"type": "log", "text": f"Processor init failed: {e}", "level": "ERROR"})
            return

        files = sorted(Path(proc.data_dir).glob("leg*.npy"))
        if not files:
            cb({"type": "log",
                "text": "No hologram files found — run collection first", "level": "WARN"})
            return

        cb({"type": "log", "text": f"Found {len(files)} holograms", "level": "INFO"})

        # Background subtraction (Caleb's tip): if enabled and a reference
        # library exists, subtract the per-wavelength reference frame before
        # reconstruction. Worth ~+0.4 pts fidelity. Off by default.
        pcfg = self.config.get("processing", {})
        bg_dir = pcfg.get("background_dir")
        bg_mod = float(pcfg.get("background_modifier", 0.8))
        subtract_bg = (bool(pcfg.get("subtract_background", False))
                       and bg_dir and Path(bg_dir).exists())
        if subtract_bg:
            cb({"type": "log",
                "text": f"Background subtraction ON (refs: {bg_dir}, modifier {bg_mod})",
                "level": "INFO"})

        summary_rows = []
        for i, fpath in enumerate(files):
            if self.stop_event.is_set():
                break

            cb({"type": "progress",
                "percent": i / len(files) * 100,
                "status":  f"Processing {fpath.name} ({i+1}/{len(files)})",
                "acq": i + 1, "total_acq": len(files)})
            cb({"type": "log", "text": f"Processing: {fpath.name}", "level": "INFO"})

            try:
                hologram = proc.load_hologram(fpath)
                wl = 1550
                meta_f = fpath.with_suffix(".yaml")
                if meta_f.exists():
                    with open(meta_f) as f:
                        wl = yaml.safe_load(f).get("wavelength_nm", 1550)

                bg = None
                if subtract_bg:
                    bgp = Path(bg_dir) / fpath.name      # same filename in refs dir
                    if bgp.exists():
                        bg = proc.load_hologram(bgp)
                    else:
                        cb({"type": "log",
                            "text": f"  (no reference for {fpath.name} — skipping bg)",
                            "level": "DEBUG"})

                results = proc.process_single_hologram(
                    hologram, wavelength_nm=wl,
                    show_plots=False, save_plots=True,
                    plot_prefix=fpath.stem, background=bg, bg_modifier=bg_mod)
                powers_str = " ".join(
                    f"{p*100:.1f}%" for p in results["mode_powers"][:5])
                cb({"type": "log",
                    "text": f"  ✓ Fidelity: {results['fidelity']:.4f}  [{powers_str}]",
                    "level": "OK"})
                summary_rows.append({
                    "filename": fpath.name,
                    "wavelength_nm": int(wl),
                    "fidelity": float(results["fidelity"]),
                    "mode_powers": [float(p) for p in results["mode_powers"]],
                })
            except Exception as e:
                import traceback
                cb({"type": "log", "text": f"  ✗ {e}", "level": "ERROR"})
                cb({"type": "log", "text": traceback.format_exc(), "level": "DEBUG"})

        # Write the summary the Results tab reads (the GUI path never did this
        # before, so Results was always empty after a run).
        try:
            from datetime import datetime as _dt
            proc.results_dir.mkdir(parents=True, exist_ok=True)
            with open(proc.results_dir / "processing_summary.yaml", "w") as f:
                yaml.dump({"processing_date": _dt.now().isoformat(),
                           "total_processed": len(summary_rows),
                           "results": summary_rows}, f, sort_keys=False)
        except Exception as e:
            cb({"type": "log", "text": f"  (couldn't write results summary: {e})", "level": "DEBUG"})

        cb({"type": "progress", "percent": 100, "status": "Processing complete"})
        cb({"type": "log", "text": "Data processing complete", "level": "OK"})

    # ── Done handler (GUI thread) ───────────────────────────────────────────────
    def _on_done(self, event: str, success: bool):
        self.experiment_running = False
        self._stop_btn.setEnabled(False)

        if event == "connect":
            ok    = getattr(self, "_connected_names", [])
            all_4 = ("Laser", "Camera", "Switch", "Motors")
            off   = [d for d in all_4 if d not in ok]

            self._connect_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(True)

            if len(ok) == 4:
                self._status_lbl.setText("All 4 devices connected — ready to run")
                self._log("All hardware connected. Press ▶ START when ready.", "OK")
            elif len(ok) == 0:
                self._status_lbl.setText("No devices connected — check cables & config")
                self._log("No devices connected. Check cables, COM ports, and GPIB address.", "ERROR")
                self._connect_btn.setEnabled(True)
                self._disconnect_btn.setEnabled(False)
            else:
                summary = f"{len(ok)}/4 connected: {', '.join(ok)}"
                missing = f"Offline: {', '.join(off)}"
                self._status_lbl.setText(f"{summary} — {missing}")
                self._log(f"{summary}", "OK")
                self._log(f"{missing} — plug in and click Connect to retry", "WARN")

            self._start_btn.setEnabled(bool(ok))
            if "Motors" in ok:
                self._sync_paddle_targets_from_hw()
        elif event == "experiment":
            self._start_btn.setEnabled(self.hardware_connected)
            if success:
                self._progress_bar.setValue(100)
                self._status_lbl.setText("Experiment complete!")
                self._refresh_results()
                QMessageBox.information(self, "Done",
                    "Experiment completed successfully!\nCheck the Results tab.")
            else:
                self._status_lbl.setText("Stopped / error — see log")

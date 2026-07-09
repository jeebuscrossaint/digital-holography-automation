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
    """Actual paddle positions read from the hardware. NOT motors.angles — that's
    the last *commanded* angle and is stale ([0,0,0]) if the app didn't move the
    paddles this session, so the saved metadata was wrong."""
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
        import numpy as np
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
        # Index the reference library by wavelength so a fine (e.g. 0.1 nm)
        # library can be reused for a data sweep at ANY step — we pick the
        # nearest-wavelength reference instead of requiring an exact filename
        # match. References are leg-independent (reference beam doesn't pass
        # through the lantern), so we key on wavelength only.
        ref_index = {}
        if subtract_bg:
            def _wl_of(name):
                # filenames encode a fractional λ as 1547p3 (not 1547.3), so the
                # token is digits + optional 'p' + digits — no literal dot, or the
                # regex would swallow the '.npy' extension's dot.
                m = re.search(r"wavelength(\d+(?:p\d+)?)", name)
                if not m:
                    return None
                try:
                    return float(m.group(1).replace("p", "."))
                except ValueError:
                    return None
            for rp in Path(bg_dir).glob("*.npy"):
                w = _wl_of(rp.name)
                if w is not None:
                    ref_index[w] = rp
            cb({"type": "log",
                "text": f"Background subtraction ON — {len(ref_index)} reference "
                        f"wavelengths in {bg_dir} (modifier {bg_mod}, nearest-λ match)",
                "level": "INFO"})

        # Auto-select reconstruction method by leg count. A MULTI-LEG dataset
        # (the fiber switch was used) unlocks the paper's cross-port multiport
        # method; a single leg can only use single-frame. We run multiport when
        # >=2 legs are present and keep, PER FRAME, whichever of {multiport,
        # single-frame} scores higher — so it can never do worse than
        # single-frame, and auto-upgrades once multiport is tuned on a real
        # good-optics leg×wavelength sweep. (On the data available today
        # multiport underperforms and this falls back to single-frame.)
        def _leg_wl(name):
            lm = re.search(r"leg(\d+)", name)
            wm = re.search(r"wavelength(\d+)", name)
            return (int(lm.group(1)) if lm else None,
                    int(wm.group(1)) if wm else None)

        legs_present = sorted({_leg_wl(f.name)[0] for f in files} - {None})
        wls_present  = sorted({_leg_wl(f.name)[1] for f in files} - {None})
        mp_frames = {}
        if len(legs_present) >= 2:
            cb({"type": "log",
                "text": f"Multi-leg dataset ({len(legs_present)} legs) — running "
                        f"multiport reconstruction (paper cross-port method)…",
                "level": "INFO"})
            try:
                from multiport_reconstruction import MultiPortReconstructor
                mp = MultiPortReconstructor(
                    proc.data_dir, legs_present, wls_present,
                    filename_fmt="leg{leg:02d}-wavelength{wl:04d}.npy",
                    crop_size=200, nfft=64, mode_size=180,
                    core_radius=12e-6, NA=0.11, n_eff=1.453,   # 7-core → 8 modes
                    diameter_range=(40, 90), pol_half=None,     # single-pol rig
                    ref_wavelength=wls_present[0])
                mp_out = mp.reconstruct_all()
                mp_frames = mp_out.get("frames", {})
                cb({"type": "log",
                    "text": f"Multiport mean fidelity "
                            f"{float(np.mean(mp_out['fidelity'])):.3f} — keeping the "
                            f"better of multiport/single-frame per frame",
                    "level": "INFO"})
            except Exception as e:
                import traceback
                cb({"type": "log",
                    "text": f"Multiport unavailable ({e}) — single-frame only",
                    "level": "WARN"})
                cb({"type": "log", "text": traceback.format_exc(), "level": "DEBUG"})

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
                if subtract_bg and ref_index:
                    nearest = min(ref_index, key=lambda w: abs(w - float(wl)))
                    if abs(nearest - float(wl)) <= 2.0:      # within 2 nm
                        bg = proc.load_hologram(ref_index[nearest])
                    else:
                        cb({"type": "log",
                            "text": f"  (nearest reference {nearest} nm too far "
                                    f"from {wl} nm — skipping bg)", "level": "DEBUG"})

                results = proc.process_single_hologram(
                    hologram, wavelength_nm=wl,
                    show_plots=False, save_plots=True,
                    plot_prefix=fpath.stem, background=bg, bg_modifier=bg_mod)

                fid = float(results["fidelity"])
                powers = [float(p) for p in results["mode_powers"]]
                engine = "single-frame"
                # Keep multiport's result for this (leg, λ) only if it wins.
                fr = mp_frames.get(_leg_wl(fpath.name))
                if fr is not None and float(fr["fidelity"]) > fid:
                    dp = np.abs(fr["decomp"]) ** 2
                    ssum = float(dp.sum())
                    powers = [float(x) for x in (dp / ssum if ssum > 0 else dp)]
                    cb({"type": "log",
                        "text": f"  ↑ multiport {float(fr['fidelity']):.4f} beats "
                                f"single-frame {fid:.4f}", "level": "OK"})
                    fid = float(fr["fidelity"])
                    engine = "multiport"

                powers_str = " ".join(f"{p*100:.1f}%" for p in powers[:5])
                cb({"type": "log",
                    "text": f"  ✓ Fidelity: {fid:.4f} ({engine})  [{powers_str}]",
                    "level": "OK"})
                summary_rows.append({
                    "filename": fpath.name,
                    "wavelength_nm": int(wl),
                    "fidelity": fid,
                    "mode_powers": powers,
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

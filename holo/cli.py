# -*- coding: utf-8 -*-
"""``holo`` -- the command-line front end.

A sibling of the GUI, not a layer under it: both call the same library and
neither owns analysis code. Every subcommand here should be a thin argument
parser plus a call into ``holo.*``.

    holo process ./data              reconstruct a folder of holograms
    holo tm ./data -o tm.npz         reconstruct + export the transfer matrix
    holo doctor                      check the install and the rig
    holo probe switch                talk to one instrument
    holo gui                         launch the desktop app

Run ``holo <command> --help`` for the options of any one command.
"""

import argparse
import sys
from pathlib import Path

from . import __version__


# ── helpers ──────────────────────────────────────────────────────────────────

def _log(text, level="INFO"):
    if level != "DEBUG":
        print(text)


def _rule(text):
    print("=" * 68)
    print(text)
    print("=" * 68)


def _load_config(path):
    from . import config as cfgmod
    return cfgmod.load(path)


# ── holo process ─────────────────────────────────────────────────────────────

def cmd_process(args):
    """Reconstruct every hologram in one or more folders."""
    from . import discovery, pipeline
    from .data_processing import HolographyDataProcessor

    config = _load_config(args.config)
    cfg_path = str(args.config) if args.config else str(__import__(
        "holo.config", fromlist=["default_path"]).default_path())

    failures = 0
    for folder in args.folders:
        folder = Path(folder)
        if not folder.is_dir():
            print(f"[{folder}] not a folder — skipping")
            failures += 1
            continue

        records, cache = discovery.stage(folder, args.wavelength)
        if not records:
            print(f"[{folder}] no holograms found — skipping")
            failures += 1
            continue

        proc = HolographyDataProcessor(config_file=cfg_path)
        proc.data_dir = cache
        proc.results_dir = folder / "processed_results"
        if not args.no_save:
            proc.results_dir.mkdir(parents=True, exist_ok=True)

        ref_index, single_bg = discovery.build_ref_index(args.background, config)
        legs = sorted({r["leg"] for r in records})
        wls = sorted({int(round(r["wl"])) for r in records})
        _rule(f"{folder}  —  {len(records)} frames, {len(legs)} legs, "
              f"{len(wls)} wavelengths")

        rows = pipeline.process_records(
            proc, records, config=config, log=_log,
            load=discovery.load_frame, background=single_bg,
            ref_index=ref_index, multiport_dir=cache,
            use_multiport=not args.single,
            save=not args.no_save, show=args.show)

        if not args.no_save:
            pipeline.write_summary(proc.results_dir, rows, folder=folder, log=_log)
        if rows:
            mean = sum(r["fidelity"] for r in rows) / len(rows)
            print(f"\n{folder}: mean fidelity {mean:.4f} over {len(rows)} frames")
            if not args.no_save:
                print(f"  -> {proc.results_dir}")
        else:
            failures += 1
    return 1 if failures else 0


# ── holo tm ──────────────────────────────────────────────────────────────────

def cmd_tm(args):
    """Reconstruct a sweep and export the wavelength-resolved transfer matrix.

    This is the actual deliverable of the experiment and there was previously
    no way to get it without the GUI.
    """
    import numpy as np
    from . import config as cfgmod, discovery
    from .multiport_reconstruction import MultiPortReconstructor

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"{folder} is not a folder", file=sys.stderr)
        return 2

    records, cache = discovery.stage(folder, args.wavelength)
    if not records:
        print(f"no holograms found in {folder}", file=sys.stderr)
        return 2

    legs = sorted({r["leg"] for r in records})
    wls = sorted({int(round(r["wl"])) for r in records})
    if len(legs) < 2:
        print(f"transfer matrix needs >= 2 legs; found {len(legs)}", file=sys.stderr)
        return 2

    mp = cfgmod.multiport(_load_config(args.config))
    _rule(f"{folder}  —  transfer matrix over {len(legs)} legs x {len(wls)} λ")

    R = MultiPortReconstructor(
        cache, legs, wls,
        filename_fmt=discovery.MULTIPORT_FMT,
        crop_size=args.crop, nfft=args.nfft, mode_size=args.mode_size,
        core_radius=float(mp.get("core_radius", 12e-6)),
        NA=float(mp.get("numerical_aperture", 0.11)),
        n_eff=float(mp.get("effective_index", 1.453)),
        diameter_range=(40, 90), pol_half=None, ref_wavelength=wls[0])

    out = R.reconstruct_all(progress=(lambda s: print("  " + s)) if args.verbose else None)
    fid = np.asarray(out["fidelity"], dtype=float)
    tm = out["transfer_matrices"]

    dest = Path(args.output) if args.output else folder / "transfer_matrix.npz"
    np.savez(dest, transfer_matrices=tm, fidelity=fid,
             wavelengths=np.asarray(wls), legs=np.asarray(legs))
    print(f"\nfidelity  mean {fid.mean()*100:.2f}%  std {fid.std()*100:.2f}%  "
          f"min {fid.min()*100:.2f}%   ({fid.size} frames)")
    print(f"transfer matrices {tm.shape}  (n_wavelength, n_mode, n_leg)")
    print(f"  -> {dest}")

    # A transfer matrix is only meaningful if the frames reconstructed. Writing
    # one at 0.2% fidelity without comment is how bad numbers reach a plot.
    if fid.mean() < 0.5:
        print(f"\n*** WARNING: mean fidelity {fid.mean()*100:.2f}% — this "
              f"transfer matrix is not usable.", file=sys.stderr)
        print("    Usually a geometry mismatch: --crop/--nfft and the "
              "processing.multiport\n    basis in the config describe THIS rig "
              "(256-px frames, 8 modes). The\n    paper's archive is 1024x1280 "
              "dual-polarisation and needs its own settings.", file=sys.stderr)
        return 1
    if fid.mean() < 0.90:
        print(f"\nnote: mean fidelity {fid.mean()*100:.2f}% is below the ~96% "
              f"this method reaches on good data.", file=sys.stderr)
    return 0


# ── holo doctor ──────────────────────────────────────────────────────────────

def cmd_doctor(args):
    """Check that the install, the config and the instruments are usable."""
    from . import runtime
    runtime.bootstrap()
    ok = True

    print(f"holo {__version__}")
    print(f"python {sys.version.split()[0]}")
    print(f"data dir  {runtime.DATA_DIR}")
    print(f"config    {runtime.CONFIG_FILE}"
          f"{'' if Path(runtime.CONFIG_FILE).exists() else '   *** MISSING ***'}")
    if not Path(runtime.CONFIG_FILE).exists():
        ok = False

    print("\nlibrary:")
    for mod, label in [("numpy", "numpy"), ("scipy", "scipy"),
                       ("matplotlib", "matplotlib"), ("yaml", "pyyaml"),
                       ("PIL", "pillow")]:
        try:
            m = __import__(mod)
            print(f"  {label:12s} {getattr(m, '__version__', 'ok')}")
        except ImportError as e:
            print(f"  {label:12s} MISSING ({e})")
            ok = False

    print("\nengines:")
    for name, path in [("single-frame", "holo.data_processing"),
                       ("multiport", "holo.multiport_reconstruction"),
                       ("pipeline", "holo.pipeline"),
                       ("fringe", "holo.fringe_detection")]:
        try:
            __import__(path)
            print(f"  {name:12s} ok")
        except Exception as e:
            print(f"  {name:12s} FAILED: {e}")
            ok = False

    print("\ninstruments (import only — not a connection test):")
    for name, path in [("camera", "holo.hardware.XenicsCam"),
                       ("laser", "holo.hardware.HPTunableLaserSource"),
                       ("switch", "holo.hardware.D700DiconSwitch"),
                       ("paddles", "holo.hardware.polMotors")]:
        try:
            __import__(path)
            print(f"  {name:12s} ok")
        except Exception as e:
            # Expected off the lab machine; a missing vendor DLL is not a
            # broken install, so this does not fail the check.
            print(f"  {name:12s} unavailable ({type(e).__name__}: "
                  f"{str(e).splitlines()[0][:60]})")

    print("\nOK" if ok else "\nPROBLEMS FOUND")
    return 0 if ok else 1


# ── holo probe ───────────────────────────────────────────────────────────────

def cmd_probe(args):
    """Talk to one instrument directly, for bring-up and debugging."""
    from . import runtime
    runtime.bootstrap()

    if args.device == "switch":
        from .hardware.D700DiconSwitch import DiconGP700
        sw = DiconGP700(args.port) if args.port else DiconGP700()
        print(sw.identify() if hasattr(sw, "identify") else "connected")
        return 0
    if args.device == "laser":
        from .hardware.HPTunableLaserSource import HPTunableLaserSource
        ls = HPTunableLaserSource(args.port) if args.port else HPTunableLaserSource()
        print(getattr(ls, "idn", lambda: "connected")())
        return 0
    if args.device == "camera":
        from .hardware.XenicsCam import dev_discovery
        for d in dev_discovery():
            print(d)
        return 0
    if args.device == "paddles":
        from .hardware import polMotors
        print(polMotors.list_devices() if hasattr(polMotors, "list_devices")
              else "polMotors imported")
        return 0
    print(f"unknown device {args.device}", file=sys.stderr)
    return 2


# ── holo gui ─────────────────────────────────────────────────────────────────

def cmd_gui(args):
    """Launch the desktop app."""
    from . import runtime
    runtime.bootstrap()
    from gui.app import main as gui_main
    gui_main()
    return 0


# ── parser ───────────────────────────────────────────────────────────────────

def build_parser():
    ap = argparse.ArgumentParser(
        prog="holo",
        description="Photonic-lantern digital holography — UCF CREOL.",
        epilog="Run 'holo <command> --help' for per-command options.")
    ap.add_argument("--version", action="version", version=f"holo {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="<command>")

    def common(p):
        p.add_argument("--config", default=None,
                       help="config file (default: experiment_config.yaml)")
        p.add_argument("--wavelength", type=float, default=1550,
                       help="fallback wavelength (nm) for frames without one")
        return p

    p = common(sub.add_parser("process", help="reconstruct a folder of holograms"))
    p.add_argument("folders", nargs="+", help="folder(s) of holograms")
    p.add_argument("--background", default=None,
                   help="reference file or folder (overrides the config)")
    p.add_argument("--show", action="store_true", help="display plots")
    p.add_argument("--no-save", action="store_true",
                   help="print fidelities, write nothing")
    p.add_argument("--single", action="store_true",
                   help="single-frame only; skip the multiport pass")
    p.set_defaults(func=cmd_process)

    p = common(sub.add_parser("tm", help="export the wavelength-resolved transfer matrix"))
    p.add_argument("folder", help="folder holding a leg x wavelength sweep")
    p.add_argument("-o", "--output", default=None, help="output .npz")
    p.add_argument("--crop", type=int, default=200)
    p.add_argument("--nfft", type=int, default=64)
    p.add_argument("--mode-size", type=int, default=180, dest="mode_size")
    p.add_argument("-v", "--verbose", action="store_true", help="per-frame progress")
    p.set_defaults(func=cmd_tm)

    p = sub.add_parser("doctor", help="check the install, config and instruments")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("probe", help="talk to one instrument")
    p.add_argument("device", choices=["switch", "laser", "camera", "paddles"])
    p.add_argument("--port", default=None, help="serial port / VISA address")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("gui", help="launch the desktop app")
    p.set_defaults(func=cmd_gui)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

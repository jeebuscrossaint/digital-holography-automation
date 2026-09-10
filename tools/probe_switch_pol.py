"""Bench check: fiber switch + polarization paddles, together, per leg.

`probe_switch.py` only proves the GP700 answers. This one closes the loop the
experiment actually needs: for every leg, route the switch there, run the
coordinate-ascent paddle optimizer against a live camera frame, and print the
best angles + fringe metric. That tells you which legs can be brought up to
usable fringe visibility and where the paddles have to sit for each.

No analysis logic lives here — it calls holo.fringe_detection.

Run (Xeneth must NOT be holding the camera):
    uv run python tools/probe_switch_pol.py                 # legs from config
    uv run python tools/probe_switch_pol.py --legs 1-7
    uv run python tools/probe_switch_pol.py --legs 1,3,5 --budget 40
    uv run python tools/probe_switch_pol.py --dry-run       # no hardware
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))      # so `import holo` works when run in-tree

from holo import config as holo_config          # noqa: E402
from holo import runtime                         # noqa: E402


def parse_legs(spec, cfg):
    """'1-7' | '1,3,5' | None -> list of leg numbers."""
    if not spec:
        legs = cfg.get("experiment", {}).get("legs", 1)
        if isinstance(legs, int):
            return list(range(1, legs + 1))
        if isinstance(legs, dict):
            return list(range(legs["start"], legs["stop"] + 1,
                              legs.get("step", 1)))
        return list(legs)
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in spec.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legs", help="e.g. 1-7 or 1,3,5 (default: config)")
    ap.add_argument("--budget", type=int, help="frames per leg for the optimizer")
    ap.add_argument("--method", help="fringe metric (default: config)")
    ap.add_argument("--threshold", type=float, help="success cutoff on the metric")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan; touch no hardware")
    args = ap.parse_args()

    cfg = holo_config.load()
    hw = cfg["hardware"]
    fd = cfg.get("experiment", {}).get("fringe_detection", {})

    legs      = parse_legs(args.legs, cfg)
    budget    = args.budget    or fd.get("max_attempts", 60)
    method    = args.method    or fd.get("check_method", "sideband")
    threshold = args.threshold if args.threshold is not None else \
        fd.get("min_visibility", 0.15)
    module     = hw["fiber_switch"].get("module", 1)
    max_travel = float(hw["polarization_motors"].get("max_travel", 160))
    settle     = cfg.get("experiment", {}).get("wait_times", {}).get(
        "after_leg_switch", 1.0)

    print(f"legs      {legs}")
    print(f"metric    {method}  (threshold {threshold})")
    print(f"budget    {budget} frames/leg  -> up to {budget * len(legs)} frames")
    print(f"paddles   0-{max_travel:.0f}deg, serial "
          f"{hw['polarization_motors']['serial_number']}")
    if args.dry_run:
        print("\n--dry-run: nothing touched.")
        return

    runtime.bootstrap()                 # Xeneth DLLs on PATH before the import
    from holo.fringe_detection import optimize_polarization_for_fringes
    from holo.hardware.D700DiconSwitch import D700DiconSwitch
    from holo.hardware.polMotors import polMotors
    from holo.hardware.XenicsCam import XenicsCam

    switch = cam = pol = None
    results = []
    try:
        switch = D700DiconSwitch(port=hw["fiber_switch"].get("port", "auto"),
                                 baudrate=hw["fiber_switch"].get("baudrate", 9600))
        print(f"switch ID: {switch.identify() or '<silent>'}")
        pol = polMotors(str(hw["polarization_motors"]["serial_number"]).encode())
        cam = XenicsCam(url=hw["camera"].get("url"),
                        exposure=hw["camera"].get("exposure_time"))

        for leg in legs:
            print(f"\n=== leg {leg} ===")
            switch.move_to_position(module, leg)
            time.sleep(settle)          # optical path settles after the switch
            ok, metric, angles = optimize_polarization_for_fringes(
                cam, pol, max_attempts=budget, method=method,
                threshold=threshold, max_travel=max_travel,
                angle_step=cfg.get("experiment", {}).get(
                    "polarization", {}).get("angle_step", 10))
            results.append((leg, ok, metric, angles))
    finally:
        for h, closer in ((cam, "closeCamera"), (pol, "close"), (switch, "close")):
            if h is not None:
                try:
                    getattr(h, closer)()
                except Exception:
                    pass

    print(f"\n--- summary ({method}, threshold {threshold}) ---")
    for leg, ok, metric, angles in results:
        print(f"  leg {leg}: {method}={metric:.4f}  paddles={angles}  "
              f"{'OK' if ok else '<-- below threshold'}")
    bad = [leg for leg, ok, _, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} legs reached threshold."
          + (f" Below: {bad}" if bad else ""))


if __name__ == "__main__":
    main()

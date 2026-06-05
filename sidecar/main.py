# -*- coding: utf-8 -*-
"""Python sidecar for the Tauri frontend.

Reads JSON-RPC requests from stdin (one per line), writes JSON-RPC
responses to stdout. Reuses the existing hardware/ drivers we spent
the whole week debugging — no rewriting.
"""

import base64
import io
import json
import math
import os
import sys
import threading
import time
import traceback
from pathlib import Path

# Make sure we can import hardware/ and lib/ siblings of this directory.
# When frozen by PyInstaller, those are unpacked under sys._MEIPASS (added via
# --add-data); otherwise they sit next to the repo root. Resolving this wrong
# is why the bundled sidecar failed with "No module named polMotors".
if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    ROOT = Path(__file__).parent.parent
for sub in ("hardware", "lib"):
    p = ROOT / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Xeneth DLL search path (needed before importing XenicsCam)
_XENETH = r"C:\Program Files\Common Files\XenICs\Runtime"
if os.path.exists(_XENETH):
    try:
        os.add_dll_directory(_XENETH)
    except (AttributeError, OSError):
        pass
    os.environ["PATH"] = _XENETH + os.pathsep + os.environ.get("PATH", "")

import yaml  # noqa: E402

# Config is editable runtime data, so it lives beside the exe (frozen) or at
# the repo root (dev) — never inside the PyInstaller bundle.
if getattr(sys, "frozen", False):
    CONFIG_FILE = Path(sys.executable).parent / "experiment_config.yaml"
else:
    CONFIG_FILE = ROOT / "experiment_config.yaml"


# ── State container ──────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.laser  = None
        self.camera = None
        self.switch = None
        self.motors = None
        self.config = self._load_config()
        self.lock = threading.RLock()
        # Experiment runner
        self.exp_running = False
        self.exp_stop    = threading.Event()
        self.exp_status  = "Idle"
        self.exp_percent = 0.0
        self.exp_leg     = None
        self.exp_wl      = None
        self.exp_acq     = 0
        self.exp_total   = 0
        self._last_frame = None
        self._last_raw = None

    def _load_config(self):
        try:
            with open(CONFIG_FILE) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def conn_state(self, obj):
        return "online" if obj is not None else "offline"

    def hardware_status(self):
        return {
            "laser":  self.conn_state(self.laser),
            "camera": self.conn_state(self.camera),
            "switch": self.conn_state(self.switch),
            "motors": self.conn_state(self.motors),
        }


STATE = State()


# ── Hardware connection helpers ──────────────────────────────────────────────

def _connect_laser():
    cfg = STATE.config.get("hardware", {}).get("laser", {})
    addr = cfg.get("gpib_address", "GPIB0::24::INSTR")
    from HPTunableLaserSource import HPTunableLaserSource
    laser = HPTunableLaserSource(addr)
    laser.changePowerUnit(cfg.get("power_unit", "UW"))
    laser.powerAmplitude(float(cfg.get("power_uw", 208)), "UW")
    laser.outputState(True)
    return laser, f"Laser {addr} output ON ({cfg.get('power_uw', 208)} µW)"


def _connect_camera():
    cfg = STATE.config.get("hardware", {}).get("camera", {})
    url = cfg.get("url", "cam://0") or "cam://0"
    from XenicsCam import xCam
    cam = xCam(url=url, exposure=cfg.get("exposure_time"))
    ser = int(cam.ser) if cam.ser else "?"
    return cam, f"Camera Xenics Bobcat 320 GigE SER:{ser}"


def _connect_switch():
    cfg = STATE.config.get("hardware", {}).get("fiber_switch", {})
    port = cfg.get("port", "COM6")
    from D700DiconSwitch import D700DiconSwitch
    sw = D700DiconSwitch(port=port, baudrate=cfg.get("baudrate", 9600))
    return sw, f"Switch Dicon GP700 {port}"


def _connect_motors():
    cfg = STATE.config.get("hardware", {}).get("polarization_motors", {})
    serial = str(cfg.get("serial_number", "38394984"))
    from polMotors import polMotors
    m = polMotors(serialNumber=serial.encode())
    return m, f"Motors Thorlabs MPC320 SN:{serial}"


# ── RPC handlers ─────────────────────────────────────────────────────────────

def h_status(_):
    return STATE.hardware_status()


def h_connect_all(_):
    msgs = []

    def _try(name, fn, attr):
        try:
            obj, msg = fn()
            setattr(STATE, attr, obj)
            msgs.append(msg)
        except Exception as e:
            msgs.append(f"{name} failed: {e}")

    threads = []
    targets = [
        ("laser",  _connect_laser,  "laser"),
        ("camera", _connect_camera, "camera"),
        ("switch", _connect_switch, "switch"),
        ("motors", _connect_motors, "motors"),
    ]
    for name, fn, attr in targets:
        if getattr(STATE, attr) is None:
            t = threading.Thread(target=_try, args=(name, fn, attr), daemon=True)
            t.start()
            threads.append(t)
    for t in threads:
        t.join()

    out = STATE.hardware_status()
    out["message"] = " · ".join(msgs)
    return out


def h_disconnect_all(_):
    with STATE.lock:
        for obj, attr in [
            (STATE.laser,  "laser"),
            (STATE.camera, "camera"),
            (STATE.switch, "switch"),
            (STATE.motors, "motors"),
        ]:
            try:
                if obj is None:
                    continue
                if attr == "laser":
                    try: obj.outputState(False)
                    except Exception: pass
                    try: obj.closeConnection()
                    except Exception: pass
                elif attr == "camera":
                    try: obj.stopCapture()
                    except Exception: pass
                    try: obj.closeCamera()
                    except Exception: pass
                elif attr == "switch":
                    try: obj.close()
                    except Exception: pass
                elif attr == "motors":
                    try: obj.close()
                    except Exception: pass
            finally:
                setattr(STATE, attr, None)
    return None


# Laser ----------------------------------------------------------------------

def h_laser_get(_):
    if STATE.laser is None:
        return {"wavelength_nm": None, "power_uw": None, "output_on": None}
    s = {"wavelength_nm": None, "power_uw": None, "output_on": None}
    try:
        wl = STATE.laser.checkWavelength()
        if isinstance(wl, (int, float)):
            s["wavelength_nm"] = float(wl)
    except Exception:
        pass
    try:
        v = float(STATE.laser.checkPowerAmplitude())
        # Infer dBm/W/uW from SIGN and MAGNITUDE, not text format — uW/W are
        # always positive, so anything negative is dBm. (The old "'e' in
        # string => watts" check turned a dBm value like "-3.01E0" into
        # -3,010,300 uW.)
        if v < 0:
            uw = 10 ** (v / 10) * 1000        # negative => dBm
        elif abs(v) < 1e-2:
            uw = v * 1e6                      # tiny +ve => watts
        elif v < 10:
            uw = 10 ** (v / 10) * 1000        # small +ve => dBm
        else:
            uw = v                            # already uW
        s["power_uw"] = float(uw)
    except Exception:
        pass
    try:
        on = STATE.laser.isOutputOn()
        s["output_on"] = "1" in str(on)
    except Exception:
        pass
    return s


def h_laser_set_wavelength(params):
    if STATE.laser is None: raise RuntimeError("Laser not connected")
    STATE.laser.changeWavelength(float(params["nm"]))


def h_laser_set_power_uw(params):
    if STATE.laser is None: raise RuntimeError("Laser not connected")
    STATE.laser.powerAmplitude(float(params["uw"]), "UW")


def h_laser_set_output(params):
    if STATE.laser is None: raise RuntimeError("Laser not connected")
    STATE.laser.outputState(bool(params["on"]))


# Switch ---------------------------------------------------------------------

def h_switch_get(_):
    if STATE.switch is None: return {"position": None}
    try:
        module = STATE.config.get("hardware", {}).get(
            "fiber_switch", {}).get("module", 1)
        pos = STATE.switch.get_position(module)
        return {"position": int(pos) if pos is not None else None}
    except Exception:
        return {"position": None}


def h_switch_to(params):
    if STATE.switch is None: raise RuntimeError("Switch not connected")
    module = STATE.config.get("hardware", {}).get("fiber_switch", {}).get("module", 1)
    STATE.switch.move_to_position(module, int(params["leg"]))


# Motors ---------------------------------------------------------------------

def h_motors_get(_):
    if STATE.motors is None:
        return {"angles": [0.0, 0.0, 0.0]}
    try:
        a = [float(STATE.motors.getPosition(p)) for p in (1, 2, 3)]
        return {"angles": a}
    except Exception:
        return {"angles": list(getattr(STATE.motors, "angles", [0.0, 0.0, 0.0]))}


def h_motor_move(params):
    if STATE.motors is None: raise RuntimeError("Motors not connected")
    STATE.motors.moveMotor(int(params["paddle"]), float(params["angle"]))


def h_motor_home(params):
    if STATE.motors is None: raise RuntimeError("Motors not connected")
    if hasattr(STATE.motors, "homeMotor"):
        STATE.motors.homeMotor(int(params["paddle"]))
    else:
        STATE.motors.moveMotor(int(params["paddle"]), 0.0)


def h_motors_home_all(_):
    if STATE.motors is None: raise RuntimeError("Motors not connected")
    for p in (1, 2, 3):
        if hasattr(STATE.motors, "homeMotor"):
            STATE.motors.homeMotor(p)
        else:
            STATE.motors.moveMotor(p, 0.0)


def h_polarization_auto_optimize(_):
    if STATE.motors is None or STATE.camera is None:
        raise RuntimeError("Need motors and camera for auto-optimize")
    from fringe_detection import optimize_polarization_for_fringes
    fd = STATE.config.get("experiment", {}).get("fringe_detection", {})
    success, metric, angles = optimize_polarization_for_fringes(
        STATE.camera, STATE.motors,
        max_attempts=int(fd.get("max_attempts", 30)),
        method=fd.get("check_method", "variance"),
        threshold=float(fd.get("min_visibility", 0.15)),
    )
    return {"success": bool(success),
            "metric": float(metric),
            "angles": [float(a) for a in angles]}


# Camera ---------------------------------------------------------------------

def h_camera_frame(_):
    if STATE.camera is None: return None
    try:
        frame = STATE.camera.getFrame()
        if frame is None: return None
        import numpy as np
        from PIL import Image
        raw = np.asarray(frame)
        STATE._last_raw = raw                     # keep raw 16-bit for snapshot
        # Saturation read so the UI can warn while aligning.
        sat = {}
        try:
            from fringe_detection import check_saturation
            val = STATE.config.get("experiment", {}).get("validation", {})
            sat = check_saturation(
                raw, sat_level=float(val.get("saturation_level", 65535)),
                sat_fraction_max=float(val.get("max_saturated_fraction", 0.001)))
        except Exception:
            pass
        arr = raw.astype(float)
        mn, mx = arr.min(), arr.max()
        if mx > mn:
            arr = (arr - mn) / (mx - mn) * 255
        arr = arr.astype(np.uint8)
        img = Image.fromarray(arr, mode="L")
        img.thumbnail((640, 480))             # keep messages small
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        STATE._last_frame = buf.getvalue()
        return {
            "width":  img.width,
            "height": img.height,
            "data":   base64.b64encode(STATE._last_frame).decode("ascii"),
            "saturated": bool(sat.get("saturated", False)),
            "fill_fraction": float(sat.get("fill_fraction", 0.0)),
            "saturated_fraction": float(sat.get("fraction", 0.0)),
        }
    except Exception:
        return None


def h_camera_set_exposure(params):
    if STATE.camera is None: raise RuntimeError("Camera not connected")
    actual = STATE.camera.setExposure(float(params["us"]))
    return {"exposure_us": float(actual)}


def h_camera_snapshot(_):
    """Save the current frame as a hologram (raw .npy + .png + .yaml metadata)
    into the data dir — the quick way to capture data without a full run."""
    if STATE.camera is None: raise RuntimeError("Camera not connected")
    import numpy as np
    import datetime
    raw = getattr(STATE, "_last_raw", None)
    if raw is None:
        raw = STATE.camera.getFrame()
    if raw is None: raise RuntimeError("No frame available")
    raw = np.asarray(raw)
    out = Path(STATE.config.get("data", {}).get("output_dir", "./holography_data"))
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = out / f"snapshot_{stamp}"
    np.save(str(base) + ".npy", raw)
    meta = {"timestamp": datetime.datetime.now().isoformat(),
            "max_value": int(raw.max()), "mean": float(raw.mean())}
    try:
        from fringe_detection import calculate_sideband_energy, check_saturation
        meta["sideband_metric"] = float(calculate_sideband_energy(raw))
        meta["saturated"] = bool(check_saturation(raw)["saturated"])
    except Exception:
        pass
    try:
        from PIL import Image
        a = raw.astype(float); mn, mx = a.min(), a.max()
        disp = (((a - mn) / (mx - mn)) * 255).astype("uint8") if mx > mn else a.astype("uint8")
        Image.fromarray(disp, mode="L").save(str(base) + ".png")
    except Exception:
        pass
    with open(str(base) + ".yaml", "w") as f:
        yaml.dump(meta, f)
    return {"file": base.name, "sideband_metric": meta.get("sideband_metric")}


# Config ---------------------------------------------------------------------

def h_config_get(_):
    return STATE.config


def h_config_set(params):
    cfg = params["cfg"]
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    STATE.config = cfg


# Experiment ----------------------------------------------------------------

def _experiment_thread(mode):
    try:
        STATE.exp_status = "Starting…"
        STATE.exp_percent = 0
        if mode in ("collect", "full"):
            _run_collection()
        if mode in ("process", "full") and not STATE.exp_stop.is_set():
            _run_processing()
        STATE.exp_status = "Stopped" if STATE.exp_stop.is_set() else "Complete"
        STATE.exp_percent = 100 if not STATE.exp_stop.is_set() else STATE.exp_percent
    except Exception as e:
        STATE.exp_status = f"Error: {e}"
    finally:
        STATE.exp_running = False


def _run_collection():
    import numpy as np
    from fringe_detection import (check_fringes_visible,
                                   optimize_polarization_for_fringes)
    cfg = STATE.config
    legs = cfg["experiment"]["legs"]
    wls  = cfg["experiment"]["wavelengths"]
    waits = cfg["experiment"]["wait_times"]
    fdet  = cfg["experiment"]["fringe_detection"]
    fmt   = cfg["data"]["filename_format"]
    out   = Path(cfg["data"]["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    module = cfg["hardware"]["fiber_switch"]["module"]
    total  = len(legs) * len(wls)
    STATE.exp_total = total
    n = 0

    for li, leg in enumerate(legs):
        if STATE.exp_stop.is_set(): break
        STATE.exp_leg = leg
        STATE.exp_status = f"Switching to leg {leg}…"
        if STATE.switch:
            STATE.switch.move_to_position(module, leg)
        time.sleep(waits["after_leg_switch"])

        for wl in wls:
            if STATE.exp_stop.is_set(): break
            n += 1
            STATE.exp_acq = n
            STATE.exp_wl  = wl
            STATE.exp_percent = (n - 1) / total * 100
            STATE.exp_status = f"Leg {leg}, λ={wl} nm — setting wavelength…"

            if STATE.laser:
                STATE.laser.changeWavelength(wl)
            time.sleep(waits["after_wavelength_change"])

            frame = STATE.camera.getFrame() if STATE.camera else None
            if frame is None:
                continue

            if fdet["enabled"]:
                ok, _ = check_fringes_visible(
                    frame, fdet["check_method"], fdet["min_visibility"])
                if not ok and STATE.motors:
                    STATE.exp_status = f"Leg {leg}, λ={wl} nm — optimizing pol…"
                    optimize_polarization_for_fringes(
                        STATE.camera, STATE.motors,
                        max_attempts=fdet["max_attempts"],
                        method=fdet["check_method"],
                        threshold=fdet["min_visibility"])
                    time.sleep(waits.get("after_polarization_adjust", 0.3))
                    frame = STATE.camera.getFrame()

            if frame is not None:
                fname = fmt.format(leg=leg, wavelength=wl)
                np.save(out / fname, frame)

            STATE.exp_percent = n / total * 100


def _run_processing():
    from data_processing import HolographyDataProcessor
    STATE.exp_status = "Processing…"
    proc = HolographyDataProcessor(config_file=str(CONFIG_FILE))
    files = sorted(Path(proc.data_dir).glob("leg*.npy"))
    if not files:
        STATE.exp_status = "No holograms to process"
        return
    for i, fp in enumerate(files):
        if STATE.exp_stop.is_set(): break
        STATE.exp_status = f"Processing {fp.name} ({i+1}/{len(files)})"
        STATE.exp_percent = i / len(files) * 100
        try:
            holo = proc.load_hologram(fp)
            proc.process_single_hologram(holo, show_plots=False, save_plots=True,
                                          plot_prefix=fp.stem)
        except Exception:
            pass


def h_experiment_start(params):
    if STATE.exp_running:
        raise RuntimeError("Experiment already running")
    STATE.exp_running = True
    STATE.exp_stop.clear()
    mode = params.get("mode", "full")
    threading.Thread(target=_experiment_thread, args=(mode,), daemon=True).start()


def h_experiment_stop(_):
    STATE.exp_stop.set()


def h_experiment_state(_):
    return {
        "running":    STATE.exp_running,
        "status":     STATE.exp_status,
        "percent":    float(STATE.exp_percent),
        "leg":        STATE.exp_leg,
        "wavelength": STATE.exp_wl,
        "acq":        STATE.exp_acq,
        "total":      STATE.exp_total,
    }


# Results --------------------------------------------------------------------

def h_results_get(_):
    data_dir = Path(STATE.config.get("data", {}).get("output_dir", "./holography_data"))
    summary = data_dir / "processed_results" / "processing_summary.yaml"
    if not summary.exists(): return {"results": []}
    try:
        with open(summary) as f:
            return yaml.safe_load(f) or {"results": []}
    except Exception:
        return {"results": []}


def h_results_open_folder(_):
    data_dir = Path(STATE.config.get("data", {}).get("output_dir", "./holography_data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(data_dir.absolute()))
    except Exception:
        pass


# ── Dispatch ─────────────────────────────────────────────────────────────────

HANDLERS = {
    "status":                       h_status,
    "connect_all":                  h_connect_all,
    "disconnect_all":               h_disconnect_all,
    "laser_get":                    h_laser_get,
    "laser_set_wavelength":         h_laser_set_wavelength,
    "laser_set_power_uw":           h_laser_set_power_uw,
    "laser_set_output":             h_laser_set_output,
    "switch_get":                   h_switch_get,
    "switch_to":                    h_switch_to,
    "motors_get":                   h_motors_get,
    "motor_move":                   h_motor_move,
    "motor_home":                   h_motor_home,
    "motors_home_all":              h_motors_home_all,
    "polarization_auto_optimize":   h_polarization_auto_optimize,
    "camera_frame":                 h_camera_frame,
    "camera_set_exposure":          h_camera_set_exposure,
    "camera_snapshot":              h_camera_snapshot,
    "config_get":                   h_config_get,
    "config_set":                   h_config_set,
    "experiment_start":             h_experiment_start,
    "experiment_stop":              h_experiment_stop,
    "experiment_state":             h_experiment_state,
    "results_get":                  h_results_get,
    "results_open_folder":          h_results_open_folder,
}


def main():
    # Unbuffered I/O so the parent process gets responses immediately
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        try:
            handler = HANDLERS.get(method)
            if not handler:
                raise RuntimeError(f"Unknown method: {method}")
            result = handler(params)
            response = {"id": req_id, "ok": True, "result": result}
        except Exception as e:
            response = {
                "id": req_id, "ok": False,
                "error": str(e),
                "trace": traceback.format_exc(),
            }
        out.write(json.dumps(response, default=str) + "\n")
        out.flush()


if __name__ == "__main__":
    main()

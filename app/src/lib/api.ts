// Talk to the Python backend over HTTP, so the UI works in any browser (e.g.
// over Tailscale to a headless NUC). The FastAPI server exposes POST /rpc with
// the same {method, params} -> {ok, result} contract the old Tauri bridge used.
export async function rpc<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
  let data: any;
  try {
    const res = await fetch("/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method, params }),
    });
    data = await res.json();
  } catch (e) {
    throw new Error(`cannot reach server (${method}): ${e}`);
  }
  if (!data || !data.ok) throw new Error(data?.error || `rpc ${method} failed`);
  return data.result as T;
}

// Convenience methods — mirror the sidecar's handlers
export const api = {
  // Connections
  connectAll:    () => rpc<HardwareStatus>("connect_all"),
  disconnectAll: () => rpc<void>("disconnect_all"),
  status:        () => rpc<HardwareStatus>("status"),

  // Laser
  laserGet:      () => rpc<LaserState>("laser_get"),
  laserSetWl:    (nm: number)   => rpc<void>("laser_set_wavelength", { nm }),
  laserSetPow:   (uw: number)   => rpc<void>("laser_set_power_uw",  { uw }),
  laserOutput:   (on: boolean)  => rpc<void>("laser_set_output", { on }),

  // Switch
  switchGet:     () => rpc<SwitchState>("switch_get"),
  switchTo:      (leg: number) => rpc<void>("switch_to", { leg }),

  // Polarization motors
  motorsGet:     () => rpc<MotorState>("motors_get"),
  motorMove:     (paddle: number, angle: number) =>
                   rpc<void>("motor_move", { paddle, angle }),
  motorHome:     (paddle: number) => rpc<void>("motor_home", { paddle }),
  motorsHomeAll: () => rpc<void>("motors_home_all"),
  autoOptimize:  () => rpc<{ success: boolean; metric: number; angles: number[] }>(
                         "polarization_auto_optimize"),

  // Camera
  cameraFrame:   () => rpc<CameraFrame | null>("camera_frame"),
  cameraSetExposure: (us: number) => rpc<{ exposure_us: number }>(
                         "camera_set_exposure", { us }),
  cameraSnapshot: () => rpc<{ file: string; sideband_metric: number | null }>(
                         "camera_snapshot"),

  // Experiment + config
  configGet:     () => rpc<any>("config_get"),
  configSet:     (cfg: any) => rpc<void>("config_set", { cfg }),
  experimentStart: (mode: string) => rpc<void>("experiment_start", { mode }),
  experimentStop:  () => rpc<void>("experiment_stop"),
  experimentState: () => rpc<ExperimentState>("experiment_state"),
};

// Types
export interface CameraFrame {
  width: number;
  height: number;
  data: string;                 // base64 PNG
  saturated?: boolean;
  fill_fraction?: number;
  saturated_fraction?: number;
}

export type ConnectionState = "offline" | "connecting" | "online" | "error";

export interface HardwareStatus {
  laser:  ConnectionState;
  camera: ConnectionState;
  switch: ConnectionState;
  motors: ConnectionState;
  message?: string;
}

export interface LaserState {
  wavelength_nm: number | null;
  power_uw:      number | null;
  output_on:     boolean | null;
}

export interface SwitchState {
  position: number | null;
}

export interface MotorState {
  angles: [number, number, number];
}

export interface ExperimentState {
  running: boolean;
  status:  string;
  percent: number;
  leg:     number | null;
  wavelength: number | null;
  acq:     number;
  total:   number;
}

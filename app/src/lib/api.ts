import { invoke } from "@tauri-apps/api/core";

// Thin wrapper around the Tauri command that pipes JSON-RPC to the Python sidecar.
export async function rpc<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
  return invoke<T>("sidecar_rpc", { method, params });
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
  cameraFrame:   () => rpc<{ width: number; height: number; data: string } | null>(
                         "camera_frame"),

  // Experiment + config
  configGet:     () => rpc<any>("config_get"),
  configSet:     (cfg: any) => rpc<void>("config_set", { cfg }),
  experimentStart: (mode: string) => rpc<void>("experiment_start", { mode }),
  experimentStop:  () => rpc<void>("experiment_stop"),
  experimentState: () => rpc<ExperimentState>("experiment_state"),
};

// Types
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

import { ReactNode } from "react";
import { Plug, PowerOff } from "lucide-react";
import { Button } from "./ui/Button";
import { cn } from "@/lib/utils";
import {
  ConnectionState, HardwareStatus,
  LaserState, SwitchState, MotorState,
} from "@/lib/api";

interface Props {
  active: string;
  onSelect: (tab: string) => void;
  status: HardwareStatus;
  laser: LaserState;
  switch_: SwitchState;
  motors: MotorState;
  connecting: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}

const DOT: Record<ConnectionState, string> = {
  online:     "bg-ok",
  offline:    "bg-faint/40",
  connecting: "bg-warn animate-pulse",
  error:      "bg-bad",
};

export function OpticalPath({
  active, onSelect, status, laser, switch_, motors,
  connecting, onConnect, onDisconnect,
}: Props) {
  const anyOnline = ["laser", "camera", "switch", "motors"].some(
    (k) => (status as any)[k] === "online"
  );

  return (
    <div className="px-7 pt-1 pb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-faint">
          Instrument chain
        </span>
        <div className="flex gap-1.5">
          <Button
            variant="primary" size="sm"
            onClick={onConnect}
            disabled={connecting || anyOnline}
          >
            <Plug className="h-3 w-3" />
            Connect
          </Button>
          <Button
            variant="outline" size="sm"
            onClick={onDisconnect}
            disabled={!anyOnline}
          >
            <PowerOff className="h-3 w-3" />
            Disconnect
          </Button>
        </div>
      </div>

      <div className="flex items-stretch gap-0">
        <Tile
          name="LASER"
          state={status.laser}
          active={active === "laser"}
          onClick={() => onSelect("laser")}
          big={laser.wavelength_nm != null ? laser.wavelength_nm.toFixed(2) : "—"}
          bigSuffix="nm"
          sub={
            laser.power_uw != null
              ? `${laser.power_uw.toFixed(0)} µW · ${laser.output_on ? "on" : "off"}`
              : "HP 8168E"
          }
        />
        <Link />
        <Tile
          name="SWITCH"
          state={status.switch}
          active={active === "switch"}
          onClick={() => onSelect("switch")}
          big={switch_.position != null ? `${switch_.position}` : "—"}
          bigSuffix={switch_.position != null ? "leg" : ""}
          sub="Dicon GP700"
        />
        <Link />
        <Tile
          name="POLARIZATION"
          state={status.motors}
          active={active === "polarization"}
          onClick={() => onSelect("polarization")}
          big={
            motors.angles.length === 3 && motors.angles.some(a => a !== 0)
              ? motors.angles.map(a => a.toFixed(0)).join("·")
              : "—"
          }
          bigSuffix="°"
          sub="MPC320"
          mono
        />
        <Link />
        <Tile
          name="CAMERA"
          state={status.camera}
          active={active === "run"}
          onClick={() => onSelect("run")}
          big={status.camera === "online" ? "live" : "—"}
          bigSuffix=""
          sub="Bobcat 320 GigE"
        />
      </div>
    </div>
  );
}

function Tile({
  name, state, active, onClick, big, bigSuffix, sub, mono,
}: {
  name: string;
  state: ConnectionState;
  active: boolean;
  onClick: () => void;
  big: ReactNode;
  bigSuffix: string;
  sub: string;
  mono?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex-1 text-left rounded-md border bg-elevated/70",
        "p-3 transition-colors min-w-0",
        active
          ? "border-accent/70 shadow-[0_0_0_1px_hsl(var(--accent)/0.4)_inset]"
          : "border-border/60 hover:border-border"
      )}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-mono tracking-[0.16em] text-faint">
          {name}
        </span>
        <span className={cn("h-1.5 w-1.5 rounded-full", DOT[state])} />
      </div>

      <div className={cn(
        "text-[22px] leading-none tabular-nums truncate",
        state !== "online" && "text-faint",
        mono && "font-mono"
      )}>
        {big}
        {bigSuffix && (
          <span className="text-xs text-faint ml-1.5 font-sans">{bigSuffix}</span>
        )}
      </div>

      <div className="text-[10px] mt-2 text-faint truncate">{sub}</div>
    </button>
  );
}

/** Thin dash between tiles. Not an arrow, not a cable — just a quiet
 *  visual continuation. */
function Link() {
  return (
    <div className="self-center px-2 text-faint/50 select-none" aria-hidden>
      <svg width="22" height="2" viewBox="0 0 22 2">
        <line
          x1="0" y1="1" x2="22" y2="1"
          stroke="currentColor" strokeDasharray="2 3" strokeWidth="1"
        />
      </svg>
    </div>
  );
}

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
  offline:    "bg-faint/50",
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
    <div className="px-7 pt-2 pb-3.5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[12px] font-semibold text-soft">
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
          name="Laser"
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
          name="Switch"
          state={status.switch}
          active={active === "switch"}
          onClick={() => onSelect("switch")}
          big={switch_.position != null ? `${switch_.position}` : "—"}
          bigSuffix={switch_.position != null ? "leg" : ""}
          sub="Dicon GP700"
        />
        <Link />
        <Tile
          name="Polarization"
          state={status.motors}
          active={active === "polarization"}
          onClick={() => onSelect("polarization")}
          big={
            motors.angles.length === 3 && motors.angles.some(a => a !== 0)
              ? motors.angles.map(a => a.toFixed(0)).join(" · ")
              : "—"
          }
          bigSuffix="°"
          sub="Thorlabs MPC320"
        />
        <Link />
        <Tile
          name="Camera"
          state={status.camera}
          active={active === "run"}
          onClick={() => onSelect("run")}
          big={status.camera === "online" ? "Live" : "—"}
          bigSuffix=""
          sub="Bobcat 320 GigE"
        />
      </div>
    </div>
  );
}

function Tile({
  name, state, active, onClick, big, bigSuffix, sub,
}: {
  name: string;
  state: ConnectionState;
  active: boolean;
  onClick: () => void;
  big: ReactNode;
  bigSuffix: string;
  sub: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex-1 text-left rounded-[8px] p-3 transition-colors min-w-0",
        active
          ? "bg-accent/10 shadow-[0_0_0_1px_hsl(var(--accent)/0.5)]"
          : "bg-elevated/70 hover:bg-elevated shadow-[0_0_0_0.5px_hsl(var(--border))]"
      )}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className={cn(
          "text-[12px] font-semibold",
          active ? "text-accent" : "text-soft"
        )}>
          {name}
        </span>
        <span className={cn("h-1.5 w-1.5 rounded-full", DOT[state])} />
      </div>

      <div className={cn(
        "text-[20px] leading-none tabular-nums truncate -tracking-[0.01em]",
        state !== "online" && "text-faint"
      )}>
        {big}
        {bigSuffix && (
          <span className="text-[12px] text-faint ml-1.5">{bigSuffix}</span>
        )}
      </div>

      <div className="text-[11px] mt-1.5 text-faint truncate">{sub}</div>
    </button>
  );
}

function Link() {
  return (
    <div className="self-center px-2 text-faint/40 select-none" aria-hidden>
      <svg width="18" height="2" viewBox="0 0 18 2">
        <line
          x1="0" y1="1" x2="18" y2="1"
          stroke="currentColor" strokeWidth="1"
        />
      </svg>
    </div>
  );
}

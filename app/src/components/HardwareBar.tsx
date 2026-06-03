import { Plug, PowerOff } from "lucide-react";
import { Button } from "./ui/Button";
import { ConnectionState, HardwareStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const DOT_STYLES: Record<ConnectionState, string> = {
  online:     "bg-ok",
  offline:    "bg-faint/60",
  connecting: "bg-warn animate-pulse",
  error:      "bg-bad",
};
const LABELS: Record<ConnectionState, string> = {
  online:     "online",
  offline:    "offline",
  connecting: "connecting…",
  error:      "error",
};

function Pill({ name, state }: { name: string; state: ConnectionState }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-panel border border-border/60">
      <span className={cn("h-2 w-2 rounded-full", DOT_STYLES[state])} />
      <span className="text-sm font-medium">{name}</span>
      <span className="text-[10px] font-mono uppercase tracking-wider text-faint">
        {LABELS[state]}
      </span>
    </div>
  );
}

export function HardwareBar({
  status,
  connecting,
  onConnect,
  onDisconnect,
}: {
  status: HardwareStatus;
  connecting: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const anyOnline = ["laser", "camera", "switch", "motors"].some(
    (k) => (status as any)[k] === "online"
  );

  return (
    <div className="px-6 py-3 flex items-center gap-3 border-b border-border">
      <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-faint mr-2">
        Hardware
      </span>
      <Pill name="Laser"  state={status.laser} />
      <Pill name="Camera" state={status.camera} />
      <Pill name="Switch" state={status.switch} />
      <Pill name="Motors" state={status.motors} />
      <div className="flex-1" />
      <Button
        variant="primary"
        size="md"
        onClick={onConnect}
        disabled={connecting || anyOnline}
      >
        <Plug className="h-4 w-4" />
        Connect All
      </Button>
      <Button
        variant="outline"
        size="md"
        onClick={onDisconnect}
        disabled={!anyOnline}
      >
        <PowerOff className="h-4 w-4" />
        Disconnect
      </Button>
    </div>
  );
}

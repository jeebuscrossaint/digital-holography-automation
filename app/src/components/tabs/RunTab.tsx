import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { Play, Square } from "lucide-react";
import { api, ExperimentState } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODES = [
  { value: "full",    label: "Full run" },
  { value: "collect", label: "Collect only" },
  { value: "process", label: "Process only" },
];

export function RunTab({
  online,
  onLog,
}: {
  online: boolean;
  onLog: (text: string, level?: "INFO" | "OK" | "WARN" | "ERROR") => void;
}) {
  const [mode, setMode] = useState("full");
  const [state, setState] = useState<ExperimentState>({
    running: false, status: "Idle", percent: 0,
    leg: null, wavelength: null, acq: 0, total: 0,
  });
  const [frameSrc, setFrameSrc] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.experimentState();
        if (alive) setState(s);
      } catch { /* ignore */ }
    };
    tick();
    const id = setInterval(tick, 500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // Camera preview poll
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const f = await api.cameraFrame();
        if (alive && f) {
          setFrameSrc(`data:image/png;base64,${f.data}`);
        }
      } catch { /* ignore */ }
    };
    const id = setInterval(tick, 500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const start = async () => {
    onLog(`Experiment started (${mode})`);
    try { await api.experimentStart(mode); }
    catch (e: any) { onLog(`Start failed: ${e}`, "WARN"); }
  };
  const stop = async () => {
    onLog("Stop requested");
    try { await api.experimentStop(); }
    catch (e: any) { onLog(`Stop failed: ${e}`, "WARN"); }
  };

  return (
    <div className="px-6 py-5 space-y-4 max-w-5xl">
      <Card>
        <CardHeader><CardTitle>Mode</CardTitle></CardHeader>
        <CardBody>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex bg-panel rounded-md p-1 gap-1">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  onClick={() => setMode(m.value)}
                  className={cn(
                    "px-4 py-1.5 rounded text-sm transition-colors",
                    mode === m.value ? "bg-elevated text-ink shadow-sm" : "text-faint hover:text-ink"
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <div className="flex-1" />
            <Button
              variant="primary" size="lg"
              disabled={!online || state.running}
              onClick={start}
            >
              <Play className="h-4 w-4" /> Start
            </Button>
            <Button
              variant="danger" size="lg"
              disabled={!state.running}
              onClick={stop}
            >
              <Square className="h-4 w-4" /> Stop
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>Progress</CardTitle></CardHeader>
        <CardBody>
          <div className="space-y-3">
            <div className="h-2 rounded-full bg-panel overflow-hidden">
              <div
                className="h-full bg-accent transition-[width] duration-300"
                style={{ width: `${state.percent}%` }}
              />
            </div>
            <div className="text-sm text-soft">{state.status}</div>
            <div className="grid grid-cols-4 gap-6 pt-2">
              <Metric label="Leg"        value={state.leg ?? "—"} />
              <Metric label="Wavelength" value={state.wavelength ? `${state.wavelength} nm` : "—"} />
              <Metric label="Images"     value={`${state.acq} / ${state.total || "—"}`} />
              <Metric label="Percent"    value={`${state.percent.toFixed(0)}%`} />
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>Camera preview</CardTitle></CardHeader>
        <CardBody>
          <div className="aspect-[4/3] w-full bg-[#0a0a0a] rounded border border-border grid place-items-center overflow-hidden">
            {frameSrc ? (
              <img src={frameSrc} alt="frame" className="max-h-full max-w-full" />
            ) : (
              <span className="text-faint text-sm">no signal</span>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-faint">{label}</div>
      <div className="text-xl tabular-nums mt-1">{value}</div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Play, Square, Camera, AlertTriangle, Maximize2, X, ZoomIn, ZoomOut, FolderOpen } from "lucide-react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
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
  const [expTarget, setExpTarget] = useState("1000");
  const [saturated, setSaturated] = useState(false);
  const [fill, setFill] = useState<number | null>(null);
  const wasSat = useRef(false);
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [outputDir, setOutputDir] = useState<string>("");

  // Load the configured output directory
  useEffect(() => {
    let alive = true;
    api.configGet()
      .then((cfg) => { if (alive) setOutputDir(cfg?.data?.output_dir ?? ""); })
      .catch(() => { /* ignore */ });
    return () => { alive = false; };
  }, []);

  const chooseFolder = async () => {
    try {
      const picked = await openDialog({ directory: true, multiple: false,
                                        defaultPath: outputDir || undefined,
                                        title: "Choose where to save holograms" });
      if (!picked || Array.isArray(picked)) return;
      const cfg = await api.configGet();
      cfg.data = cfg.data ?? {};
      cfg.data.output_dir = picked;
      await api.configSet(cfg);
      setOutputDir(picked);
      onLog(`Saving data to: ${picked}`, "OK");
    } catch (e: any) {
      onLog(`Folder pick failed: ${e}`, "WARN");
    }
  };

  // Esc closes the expanded view
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

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
          setSaturated(!!f.saturated);
          setFill(f.fill_fraction ?? null);
          // Log only on the not-saturated -> saturated transition.
          if (f.saturated && !wasSat.current) {
            onLog(`⚠ Camera saturating — ${((f.saturated_fraction ?? 0) * 100).toFixed(2)}% `
                  + `of pixels clipped. Lower exposure or laser power.`, "WARN");
          } else if (!f.saturated && wasSat.current) {
            onLog("✓ Saturation cleared.", "OK");
          }
          wasSat.current = !!f.saturated;
        }
      } catch { /* ignore */ }
    };
    const id = setInterval(tick, 500);
    return () => { alive = false; clearInterval(id); };
  }, [onLog]);

  const setExposure = async () => {
    const v = parseFloat(expTarget);
    if (!isFinite(v)) return;
    onLog(`Camera exposure → ${v.toFixed(0)} µs`);
    try {
      const r = await api.cameraSetExposure(v);
      onLog(`Exposure now ${r.exposure_us.toFixed(0)} µs`, "OK");
    } catch (e: any) { onLog(`Set exposure failed: ${e}`, "WARN"); }
  };

  const snapshot = async () => {
    try {
      const r = await api.cameraSnapshot();
      const sb = r.sideband_metric != null ? `  (sideband=${r.sideband_metric.toFixed(0)})` : "";
      onLog(`📷 Saved ${r.file}.npy (+png +yaml)${sb}`, "OK");
    } catch (e: any) { onLog(`Snapshot failed: ${e}`, "WARN"); }
  };

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

          {/* Where data gets saved — confirm/change before each run */}
          <div className="flex items-center gap-3 mt-4 pt-4 border-t border-border/60">
            <span className="text-xs text-faint font-mono uppercase tracking-wider whitespace-nowrap">
              Save to
            </span>
            <span className="flex-1 min-w-0 truncate text-sm text-soft font-mono"
                  title={outputDir}>
              {outputDir || "—"}
            </span>
            <Button variant="outline" disabled={state.running} onClick={chooseFolder}>
              <FolderOpen className="h-4 w-4" /> Choose…
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
          <div className="flex items-center gap-3 flex-wrap mb-3">
            <span className="text-xs text-faint font-mono uppercase tracking-wider">Exposure</span>
            <Input
              className="w-28"
              value={expTarget}
              onChange={(e) => setExpTarget(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setExposure()}
            />
            <span className="text-xs text-faint">µs</span>
            <Button variant="primary" disabled={!online} onClick={setExposure}>Set</Button>
            <Button variant="outline" disabled={!online} onClick={snapshot}>
              <Camera className="h-4 w-4" /> Save snapshot
            </Button>
            <Button variant="outline" disabled={!frameSrc}
                    onClick={() => { setZoom(1); setExpanded(true); }}>
              <Maximize2 className="h-4 w-4" /> Expand
            </Button>
            <div className="flex-1" />
            {fill != null && (
              <span className={cn(
                "text-xs tabular-nums",
                saturated ? "text-warn" : "text-faint"
              )}>
                fill {(fill * 100).toFixed(0)}%
              </span>
            )}
            {saturated && (
              <span className="flex items-center gap-1 text-xs text-warn font-medium">
                <AlertTriangle className="h-3.5 w-3.5" /> SATURATING
              </span>
            )}
          </div>
          <div
            className={cn(
              "aspect-[4/3] w-full bg-[#0a0a0a] rounded border grid place-items-center overflow-hidden",
              saturated ? "border-warn" : "border-border",
              frameSrc && "cursor-zoom-in"
            )}
            onClick={() => frameSrc && (setZoom(1), setExpanded(true))}
            title={frameSrc ? "Click to expand" : undefined}
          >
            {frameSrc ? (
              <img src={frameSrc} alt="frame" className="max-h-full max-w-full"
                   style={{ imageRendering: "pixelated" }} />
            ) : (
              <span className="text-faint text-sm">no signal</span>
            )}
          </div>
        </CardBody>
      </Card>

      {/* Fullscreen camera view for close inspection (Esc or click ✕ to exit) */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/95 flex flex-col"
          onClick={() => setExpanded(false)}
        >
          <div className="flex items-center gap-3 p-3 text-soft"
               onClick={(e) => e.stopPropagation()}>
            <span className="text-sm font-medium">Camera — live</span>
            {fill != null && (
              <span className={cn("text-xs tabular-nums", saturated ? "text-warn" : "text-faint")}>
                fill {(fill * 100).toFixed(0)}%
              </span>
            )}
            {saturated && (
              <span className="flex items-center gap-1 text-xs text-warn font-medium">
                <AlertTriangle className="h-3.5 w-3.5" /> SATURATING
              </span>
            )}
            <div className="flex-1" />
            <Button variant="outline" size="icon"
                    onClick={() => setZoom((z) => Math.max(1, z - 0.5))}>
              <ZoomOut className="h-4 w-4" />
            </Button>
            <span className="text-xs tabular-nums w-12 text-center">{zoom.toFixed(1)}×</span>
            <Button variant="outline" size="icon"
                    onClick={() => setZoom((z) => Math.min(8, z + 0.5))}>
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="icon" onClick={() => setExpanded(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 min-h-0 overflow-auto grid place-items-center p-4"
               onClick={(e) => e.stopPropagation()}>
            {frameSrc && (
              <img
                src={frameSrc}
                alt="camera"
                style={{
                  imageRendering: "pixelated",
                  transform: `scale(${zoom})`,
                  transformOrigin: "center",
                  maxHeight: "100%", maxWidth: "100%",
                }}
              />
            )}
          </div>
        </div>
      )}
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

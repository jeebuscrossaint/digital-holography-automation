import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Slider } from "../ui/Slider";
import { ChevronLeft, ChevronRight, Home } from "lucide-react";
import { api } from "@/lib/api";

type Angles = [number, number, number];

export function PolarizationTab({
  online,
  cameraOnline,
  onLog,
}: {
  online: boolean;
  cameraOnline: boolean;
  onLog: (text: string, level?: "INFO" | "OK" | "WARN" | "ERROR") => void;
}) {
  const [angles, setAngles] = useState<Angles>([0, 0, 0]);
  const [targets, setTargets] = useState<Angles>([0, 0, 0]);
  const [jog, setJog] = useState("1");
  const [optimizing, setOptimizing] = useState(false);

  useEffect(() => {
    if (!online) return;
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.motorsGet();
        if (alive) setAngles(s.angles);
      } catch { /* ignore */ }
    };
    tick();
    const id = setInterval(tick, 300);
    return () => { alive = false; clearInterval(id); };
  }, [online]);

  const setTarget = (i: number, v: number) =>
    setTargets((prev) => prev.map((a, j) => (j === i ? v : a)) as Angles);

  const move = async (paddle: 1 | 2 | 3, angle: number) => {
    const clamped = Math.max(0, Math.min(160, angle));
    setAngles((prev) => prev.map((a, j) => (j === paddle - 1 ? clamped : a)) as Angles);
    setTarget(paddle - 1, clamped);
    onLog(`Paddle ${paddle} → ${clamped.toFixed(1)}°`);
    try { await api.motorMove(paddle, clamped); } catch (e: any) { onLog(`Paddle ${paddle} move failed: ${e}`, "WARN"); }
  };

  const home = async (paddle: 1 | 2 | 3) => {
    onLog(`Paddle ${paddle} home`);
    try { await api.motorHome(paddle); } catch (e: any) { onLog(`Paddle ${paddle} home failed: ${e}`, "WARN"); }
  };

  const jogPaddle = async (paddle: 1 | 2 | 3, dir: 1 | -1) => {
    const step = parseFloat(jog) || 1;
    const cur = angles[paddle - 1];
    move(paddle, cur + dir * step);
  };

  const homeAll = async () => {
    onLog("Homing all paddles");
    try { await api.motorsHomeAll(); } catch (e: any) { onLog(`Home all failed: ${e}`, "WARN"); }
  };

  const optimize = async () => {
    if (!cameraOnline) {
      onLog("Auto-optimize needs the camera too", "WARN"); return;
    }
    setOptimizing(true);
    onLog("Auto-optimizing polarization for fringes…");
    try {
      const r = await api.autoOptimize();
      onLog(
        `${r.success ? "✓" : "⚠"} Auto-optimize: paddles=${r.angles.map((a) => a.toFixed(1)).join(", ")}, metric=${r.metric.toFixed(3)}`,
        r.success ? "OK" : "WARN"
      );
    } catch (e: any) {
      onLog(`Auto-optimize failed: ${e}`, "WARN");
    } finally {
      setOptimizing(false);
    }
  };

  return (
    <div className="px-6 py-5 space-y-4 max-w-4xl">
      <p className="text-xs text-faint">
        Thorlabs MPC320 · three motorized paddles squeeze the fiber to tune polarization.
        Auto-optimize sweeps until the camera sees max fringe visibility.
      </p>

      <div className="flex items-center gap-3">
        <span className="text-xs text-faint font-mono uppercase tracking-wider">Jog step</span>
        <Input className="w-20" value={jog} onChange={(e) => setJog(e.target.value)} />
        <span className="text-xs text-faint">°</span>
      </div>

      {[1, 2, 3].map((p) => {
        const idx = p - 1;
        return (
          <Card key={p}>
            <CardHeader>
              <CardTitle>Paddle {p}</CardTitle>
              <span className="text-3xl font-light tabular-nums">
                {angles[idx].toFixed(1)}<span className="text-base text-faint ml-1">°</span>
              </span>
            </CardHeader>
            <CardBody>
              <div className="flex items-center gap-4">
                <Slider
                  min={0}
                  max={160}
                  step={0.5}
                  value={targets[idx]}
                  onChange={(e) => setTarget(idx, parseFloat(e.target.value))}
                  onMouseUp={() => move(p as 1 | 2 | 3, targets[idx])}
                  onKeyUp={() => move(p as 1 | 2 | 3, targets[idx])}
                  disabled={!online}
                  className="flex-1"
                />
                <span className="text-xs text-faint font-mono tabular-nums w-12 text-right">
                  → {targets[idx].toFixed(0)}°
                </span>
                <Button variant="outline" size="icon" disabled={!online}
                        onClick={() => jogPaddle(p as 1 | 2 | 3, -1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button variant="outline" size="icon" disabled={!online}
                        onClick={() => jogPaddle(p as 1 | 2 | 3, 1)}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button variant="outline" disabled={!online} onClick={() => home(p as 1 | 2 | 3)}>
                  <Home className="h-3.5 w-3.5" /> Home
                </Button>
              </div>
            </CardBody>
          </Card>
        );
      })}

      <div className="flex gap-3 pt-2">
        <Button variant="outline" disabled={!online} onClick={homeAll}>Home all</Button>
        <Button variant="primary" disabled={!online || optimizing} onClick={optimize}>
          {optimizing ? "Optimizing…" : "Auto-optimize for fringes"}
        </Button>
      </div>
    </div>
  );
}

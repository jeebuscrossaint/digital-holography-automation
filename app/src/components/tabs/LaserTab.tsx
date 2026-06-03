import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { api, LaserState } from "@/lib/api";

export function LaserTab({
  online,
  onLog,
}: {
  online: boolean;
  onLog: (text: string, level?: "INFO" | "OK" | "WARN" | "ERROR") => void;
}) {
  const [state, setState] = useState<LaserState>({
    wavelength_nm: null, power_uw: null, output_on: null,
  });
  const [wlTarget, setWlTarget] = useState("1550");
  const [pwTarget, setPwTarget] = useState("208");

  useEffect(() => {
    if (!online) return;
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.laserGet();
        if (alive) setState(s);
      } catch { /* ignore */ }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(id); };
  }, [online]);

  const setWl = async () => {
    const v = parseFloat(wlTarget);
    if (!isFinite(v)) return;
    onLog(`Laser λ → ${v.toFixed(2)} nm`);
    setState((s) => ({ ...s, wavelength_nm: v }));
    try { await api.laserSetWl(v); } catch (e: any) { onLog(`Set λ failed: ${e}`, "WARN"); }
  };
  const setPw = async () => {
    const v = parseFloat(pwTarget);
    if (!isFinite(v)) return;
    onLog(`Laser P → ${v.toFixed(0)} µW`);
    setState((s) => ({ ...s, power_uw: v }));
    try { await api.laserSetPow(v); } catch (e: any) { onLog(`Set P failed: ${e}`, "WARN"); }
  };
  const toggleOut = async (on: boolean) => {
    onLog(`Laser output → ${on ? "ON" : "OFF"}`);
    setState((s) => ({ ...s, output_on: on }));
    try { await api.laserOutput(on); } catch (e: any) { onLog(`Output toggle failed: ${e}`, "WARN"); }
  };

  return (
    <div className="px-6 py-5 space-y-4 max-w-4xl">
      <p className="text-xs text-faint">
        HP 8168E tunable laser · 1475–1575 nm · SCPI over GPIB
      </p>

      <Card>
        <CardHeader><CardTitle>Wavelength</CardTitle></CardHeader>
        <CardBody>
          <div className="flex items-center gap-6">
            <div className="text-4xl font-light tabular-nums min-w-[6.5rem]">
              {state.wavelength_nm?.toFixed(2) ?? "—"}
              <span className="text-base text-faint ml-2">nm</span>
            </div>
            <div className="flex items-center gap-2">
              <Input
                className="w-32"
                value={wlTarget}
                onChange={(e) => setWlTarget(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && setWl()}
              />
              <Button variant="primary" disabled={!online} onClick={setWl}>Set λ</Button>
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>Power</CardTitle></CardHeader>
        <CardBody>
          <div className="flex items-center gap-6">
            <div className="text-4xl font-light tabular-nums min-w-[6.5rem]">
              {state.power_uw?.toFixed(0) ?? "—"}
              <span className="text-base text-faint ml-2">µW</span>
            </div>
            <div className="flex items-center gap-2">
              <Input
                className="w-28"
                value={pwTarget}
                onChange={(e) => setPwTarget(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && setPw()}
              />
              <Button variant="primary" disabled={!online} onClick={setPw}>Set P</Button>
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>Output</CardTitle></CardHeader>
        <CardBody>
          <div className="flex items-center gap-6">
            <div className={"text-4xl font-light min-w-[6.5rem] " +
              (state.output_on ? "text-ok" : state.output_on === false ? "text-faint" : "")}>
              {state.output_on == null ? "—" : state.output_on ? "ON" : "OFF"}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="primary" disabled={!online} onClick={() => toggleOut(true)}>
                Turn ON
              </Button>
              <Button variant="outline" disabled={!online} onClick={() => toggleOut(false)}>
                Turn OFF
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

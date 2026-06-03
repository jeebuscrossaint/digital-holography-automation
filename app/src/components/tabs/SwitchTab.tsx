import { useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { api, SwitchState } from "@/lib/api";

export function SwitchTab({
  online,
  state,
  legs = [1, 2, 3, 4, 5, 6, 7],
  onLog,
}: {
  online: boolean;
  state: SwitchState;
  legs?: number[];
  onLog: (text: string, level?: "INFO" | "OK" | "WARN" | "ERROR") => void;
}) {
  const [target, setTarget] = useState("1");

  const goTo = async (leg: number) => {
    onLog(`Switch → leg ${leg}`);
    try { await api.switchTo(leg); } catch (e: any) { onLog(`Switch failed: ${e}`, "WARN"); }
  };

  return (
    <div className="px-6 py-5 space-y-4 max-w-4xl">
      <p className="text-xs text-faint">
        Dicon GP700 fiber switch · routes input fiber to one of N legs of the photonic lantern
      </p>

      <Card>
        <CardHeader><CardTitle>Current leg</CardTitle></CardHeader>
        <CardBody>
          <div className="flex items-center gap-6">
            <div className="text-5xl font-light tabular-nums min-w-[4rem]">
              {state.position ?? "—"}
            </div>
            <div className="flex items-center gap-2">
              <Input
                className="w-20"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const v = parseInt(target);
                    if (Number.isFinite(v)) goTo(v);
                  }
                }}
              />
              <Button
                variant="primary"
                disabled={!online}
                onClick={() => {
                  const v = parseInt(target);
                  if (Number.isFinite(v)) goTo(v);
                }}
              >
                Move
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>Quick select</CardTitle></CardHeader>
        <CardBody>
          <div className="flex flex-wrap gap-2">
            {legs.map((leg) => (
              <Button
                key={leg}
                variant={state.position === leg ? "primary" : "outline"}
                disabled={!online}
                onClick={() => goTo(leg)}
              >
                Leg {leg}
              </Button>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

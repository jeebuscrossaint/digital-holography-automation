import { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { api } from "@/lib/api";

const FIELDS: Array<{ key: string; label: string; placeholder?: string }> = [
  { key: "hardware.laser.gpib_address",                label: "Laser GPIB address" },
  { key: "hardware.laser.power_uw",                    label: "Laser power (µW)" },
  { key: "hardware.camera.url",                        label: "Camera URL" },
  { key: "hardware.camera.exposure_time",              label: "Camera exposure (µs)" },
  { key: "hardware.fiber_switch.port",                 label: "Fiber switch COM port" },
  { key: "hardware.polarization_motors.serial_number", label: "Motor serial number" },
  { key: "experiment.legs",                            label: "Legs (comma-separated)" },
  { key: "experiment.wavelengths",                     label: "Wavelengths (nm, comma-sep)" },
  { key: "experiment.wait_times.after_leg_switch",     label: "Wait after leg switch (s)" },
  { key: "experiment.wait_times.after_wavelength_change", label: "Wait after wavelength (s)" },
  { key: "experiment.fringe_detection.min_visibility", label: "Min fringe visibility" },
  { key: "experiment.fringe_detection.max_attempts",   label: "Max polarization attempts" },
  { key: "data.output_dir",                            label: "Data output directory" },
];

function get(obj: any, path: string): any {
  return path.split(".").reduce((o, k) => (o ?? {})[k], obj);
}
function set(obj: any, path: string, value: any) {
  const keys = path.split(".");
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (typeof cur[keys[i]] !== "object" || cur[keys[i]] === null) cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
}

export function ConfigTab({
  onLog,
}: {
  onLog: (text: string, level?: "INFO" | "OK" | "WARN" | "ERROR") => void;
}) {
  const [config, setConfig] = useState<any>({});
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    (async () => {
      try {
        const cfg = await api.configGet();
        setConfig(cfg);
        const vs: Record<string, string> = {};
        for (const f of FIELDS) {
          const v = get(cfg, f.key);
          vs[f.key] = Array.isArray(v) ? v.join(",") : v == null ? "" : String(v);
        }
        setValues(vs);
      } catch (e: any) {
        onLog(`Config load failed: ${e}`, "WARN");
      }
    })();
  }, []);

  const save = async () => {
    const next = JSON.parse(JSON.stringify(config));
    for (const f of FIELDS) {
      const raw = values[f.key] ?? "";
      let parsed: any = raw.trim();
      if (parsed.includes(",")) {
        parsed = parsed.split(",")
          .map((s: string) => s.trim()).filter(Boolean)
          .map((s: string) => isFinite(+s) ? +s : s);
      } else if (parsed !== "" && /^-?\d+(\.\d+)?$/.test(parsed)) {
        parsed = +parsed;
      }
      set(next, f.key, parsed);
    }
    try {
      await api.configSet(next);
      setConfig(next);
      onLog("Configuration saved", "OK");
    } catch (e: any) {
      onLog(`Save failed: ${e}`, "WARN");
    }
  };

  return (
    <div className="px-6 py-5 space-y-4 max-w-3xl">
      <Card>
        <CardHeader><CardTitle>Settings</CardTitle></CardHeader>
        <CardBody>
          <div className="space-y-3">
            {FIELDS.map((f) => (
              <div key={f.key} className="grid grid-cols-[14rem_1fr] items-center gap-3">
                <label className="text-sm text-soft">{f.label}</label>
                <Input
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                />
              </div>
            ))}
          </div>
          <div className="pt-5">
            <Button variant="primary" onClick={save}>Save configuration</Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

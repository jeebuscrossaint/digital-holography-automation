import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { TitleBar } from "./components/TitleBar";
import { OpticalPath } from "./components/OpticalPath";
import { LogPanel, LogEntry } from "./components/LogPanel";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/Tabs";
import { LaserTab } from "./components/tabs/LaserTab";
import { SwitchTab } from "./components/tabs/SwitchTab";
import { PolarizationTab } from "./components/tabs/PolarizationTab";
import { RunTab } from "./components/tabs/RunTab";
import { ConfigTab } from "./components/tabs/ConfigTab";
import { ResultsTab } from "./components/tabs/ResultsTab";
import { useTheme } from "./lib/theme";
import {
  api, HardwareStatus, LaserState, SwitchState, MotorState,
} from "./lib/api";

export default function App() {
  const { theme, toggle } = useTheme();
  const [tab, setTab] = useState<string>("run");

  const [status, setStatus] = useState<HardwareStatus>({
    laser: "offline", camera: "offline", switch: "offline", motors: "offline",
  });
  const [laser,  setLaser]  = useState<LaserState>({
    wavelength_nm: null, power_uw: null, output_on: null,
  });
  const [switch_, setSwitch] = useState<SwitchState>({ position: null });
  const [motors, setMotors] = useState<MotorState>({ angles: [0, 0, 0] });

  const [connecting, setConnecting] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);

  const onLog = useCallback(
    (text: string, level: "INFO" | "OK" | "WARN" | "ERROR" | "DEBUG" = "INFO") => {
      const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
      setLog((prev) => [...prev, { ts, level, text }].slice(-500));
    },
    []
  );

  // Reveal the hidden Tauri window once React has painted at least once
  const shown = useRef(false);
  useEffect(() => {
    if (shown.current) return;
    shown.current = true;
    (async () => {
      try {
        const w = getCurrentWindow();
        await w.show();
        await w.setFocus();
      } catch { /* fine in non-tauri dev */ }
    })();
  }, []);

  // Central poll: hardware status + key live values for every device.
  // Tabs read from these props rather than running their own pollers.
  useEffect(() => {
    let alive = true;
    let tick = 0;

    const poll = async () => {
      try {
        const s = await api.status();
        if (!alive) return;
        setStatus(s);

        // Paddle angles — fast, returns from Kinesis cache
        if (s.motors === "online") {
          try { setMotors(await api.motorsGet()); } catch { /* ignore */ }
        }

        // Slow channels — every ~10 ticks (~3 s)
        if (tick % 10 === 0 && s.laser === "online") {
          try { setLaser(await api.laserGet()); } catch { /* ignore */ }
        }
        if (tick % 8 === 0 && s.switch === "online") {
          try { setSwitch(await api.switchGet()); } catch { /* ignore */ }
        }
      } catch { /* sidecar might still be warming up */ }
      tick++;
    };

    poll();
    const id = setInterval(poll, 300);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const connectAll = async () => {
    setConnecting(true);
    onLog("Connecting to hardware…", "INFO");
    try {
      const result = await api.connectAll();
      setStatus(result);
      const online = (Object.entries(result) as Array<[keyof HardwareStatus, any]>)
        .filter(([k, v]) => k !== "message" && v === "online").map(([k]) => k);
      onLog(`Connected: ${online.length ? online.join(", ") : "none"}`,
            online.length > 0 ? "OK" : "WARN");
      if (result.message) onLog(result.message, "INFO");
    } catch (e: any) {
      onLog(`Connect failed: ${e}`, "ERROR");
    } finally {
      setConnecting(false);
    }
  };

  const disconnectAll = async () => {
    onLog("Disconnecting hardware…", "INFO");
    try { await api.disconnectAll(); }
    catch (e: any) { onLog(`Disconnect failed: ${e}`, "WARN"); }
  };

  return (
    <div className="h-full flex flex-col bg-bg text-ink font-sans">
      <TitleBar theme={theme} onToggleTheme={toggle} />

      <div className="px-6 pt-5 pb-1 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold tracking-tight">
          Photonic Lantern Holography
        </h1>
        <span className="text-xs font-mono uppercase tracking-wider text-faint">
          UCF · CREOL
        </span>
      </div>

      <OpticalPath
        active={tab}
        onSelect={setTab}
        status={status}
        laser={laser}
        switch_={switch_}
        motors={motors}
        connecting={connecting}
        onConnect={connectAll}
        onDisconnect={disconnectAll}
      />

      <div className="flex-1 flex min-h-0 border-t border-border">
        <div className="flex-1 min-w-0 flex flex-col">
          <Tabs value={tab} onValueChange={setTab} defaultValue="run">
            <TabsList>
              <TabsTrigger value="run">Run</TabsTrigger>
              <TabsTrigger value="laser">Laser</TabsTrigger>
              <TabsTrigger value="switch">Switch</TabsTrigger>
              <TabsTrigger value="polarization">Polarization</TabsTrigger>
              <TabsTrigger value="config">Configuration</TabsTrigger>
              <TabsTrigger value="results">Results</TabsTrigger>
            </TabsList>
            <TabsContent value="run">
              <RunTab online={status.camera === "online"} onLog={onLog} />
            </TabsContent>
            <TabsContent value="laser">
              <LaserTab
                online={status.laser === "online"}
                state={laser}
                onLog={onLog}
              />
            </TabsContent>
            <TabsContent value="switch">
              <SwitchTab
                online={status.switch === "online"}
                state={switch_}
                onLog={onLog}
              />
            </TabsContent>
            <TabsContent value="polarization">
              <PolarizationTab
                online={status.motors === "online"}
                cameraOnline={status.camera === "online"}
                state={motors}
                onLog={onLog}
              />
            </TabsContent>
            <TabsContent value="config">
              <ConfigTab onLog={onLog} />
            </TabsContent>
            <TabsContent value="results">
              <ResultsTab />
            </TabsContent>
          </Tabs>
        </div>
        <LogPanel entries={log} onClear={() => setLog([])} />
      </div>
    </div>
  );
}

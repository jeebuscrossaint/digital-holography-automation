import { useCallback, useEffect, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { TitleBar } from "./components/TitleBar";
import { HardwareBar } from "./components/HardwareBar";
import { LogPanel, LogEntry } from "./components/LogPanel";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/Tabs";
import { LaserTab } from "./components/tabs/LaserTab";
import { SwitchTab } from "./components/tabs/SwitchTab";
import { PolarizationTab } from "./components/tabs/PolarizationTab";
import { RunTab } from "./components/tabs/RunTab";
import { ConfigTab } from "./components/tabs/ConfigTab";
import { ResultsTab } from "./components/tabs/ResultsTab";
import { useTheme } from "./lib/theme";
import { api, HardwareStatus } from "./lib/api";

export default function App() {
  const { theme, toggle } = useTheme();
  const [status, setStatus] = useState<HardwareStatus>({
    laser: "offline", camera: "offline", switch: "offline", motors: "offline",
  });
  const [connecting, setConnecting] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);

  const onLog = useCallback(
    (text: string, level: "INFO" | "OK" | "WARN" | "ERROR" | "DEBUG" = "INFO") => {
      const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
      setLog((prev) => [...prev, { ts, level, text }].slice(-500));
    },
    []
  );

  // Reveal the (hidden) Tauri window as soon as the React tree is mounted
  useEffect(() => {
    (async () => {
      try {
        const win = getCurrentWindow();
        await win.show();
        await win.setFocus();
      } catch { /* fine in browser dev */ }
    })();
  }, []);

  // Poll backend status
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.status();
        if (alive) setStatus(s);
      } catch { /* sidecar maybe not ready yet */ }
    };
    tick();
    const id = setInterval(tick, 1500);
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

      <div className="px-6 pt-5 pb-3 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Photonic Lantern Holography</h1>
        <span className="text-xs font-mono uppercase tracking-wider text-faint">
          UCF · CREOL
        </span>
      </div>

      <HardwareBar
        status={status}
        connecting={connecting}
        onConnect={connectAll}
        onDisconnect={disconnectAll}
      />

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 min-w-0 flex flex-col">
          <Tabs defaultValue="run">
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
              <LaserTab online={status.laser === "online"} onLog={onLog} />
            </TabsContent>
            <TabsContent value="switch">
              <SwitchTab online={status.switch === "online"} onLog={onLog} />
            </TabsContent>
            <TabsContent value="polarization">
              <PolarizationTab
                online={status.motors === "online"}
                cameraOnline={status.camera === "online"}
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

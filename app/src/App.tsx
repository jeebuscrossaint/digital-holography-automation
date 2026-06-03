import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { TitleBar } from "./components/TitleBar";
import { Sidebar, NAV_ITEMS } from "./components/Sidebar";
import { OpticalPath } from "./components/OpticalPath";
import { LogPanel, LogEntry } from "./components/LogPanel";
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

  const shown = useRef(false);
  useEffect(() => {
    if (shown.current) return;
    shown.current = true;
    (async () => {
      try { const w = getCurrentWindow(); await w.show(); await w.setFocus(); }
      catch { /* fine in browser */ }
    })();
  }, []);

  useEffect(() => {
    let alive = true;
    let tick = 0;
    const poll = async () => {
      try {
        const s = await api.status();
        if (!alive) return;
        setStatus(s);
        if (s.motors === "online") {
          try { setMotors(await api.motorsGet()); } catch { /* ignore */ }
        }
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

  const pageTitle = NAV_ITEMS.find((n) => n.id === tab)?.label ?? "";

  return (
    <div className="h-full flex flex-col text-ink font-sans">
      <TitleBar theme={theme} onToggleTheme={toggle} />

      <div className="flex-1 flex min-h-0">
        <Sidebar active={tab} onSelect={setTab} />

        <main className="flex-1 min-w-0 flex flex-col">
          {/* page header */}
          <div className="px-7 pt-5 pb-3">
            <div className="flex items-baseline gap-3">
              <h1 className="text-[17px] font-semibold tracking-[-0.02em]">
                {pageTitle}
              </h1>
              <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-faint">
                UCF · CREOL
              </span>
            </div>
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

          <div className="flex-1 min-h-0 overflow-auto border-t border-border/60">
            {tab === "run"          && <RunTab          online={status.camera === "online"} onLog={onLog} />}
            {tab === "laser"        && <LaserTab        online={status.laser  === "online"} state={laser}  onLog={onLog} />}
            {tab === "switch"       && <SwitchTab       online={status.switch === "online"} state={switch_} onLog={onLog} />}
            {tab === "polarization" && <PolarizationTab online={status.motors === "online"} cameraOnline={status.camera === "online"} state={motors} onLog={onLog} />}
            {tab === "config"       && <ConfigTab       onLog={onLog} />}
            {tab === "results"      && <ResultsTab />}
          </div>
        </main>

        <LogPanel entries={log} onClear={() => setLog([])} />
      </div>
    </div>
  );
}

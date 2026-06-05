import { useCallback, useEffect, useRef, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { sendNotification, isPermissionGranted, requestPermission } from "@tauri-apps/plugin-notification";
import { useShortcuts } from "./lib/shortcuts";
import { isTauri } from "./lib/platform";
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
  api, rpc, HardwareStatus, LaserState, SwitchState, MotorState,
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

  const startExp = useCallback(async () => {
    try { await api.experimentStart("full"); onLog("Experiment started", "INFO"); }
    catch (e: any) { onLog(`Start failed: ${e}`, "WARN"); }
  }, [onLog]);

  const stopExp = useCallback(async () => {
    try { await api.experimentStop(); onLog("Stop requested", "INFO"); }
    catch (e: any) { onLog(`Stop failed: ${e}`, "WARN"); }
  }, [onLog]);

  // Keyboard shortcuts (fallback / works even without visible menu bar)
  useShortcuts({
    onTab: setTab,
    onTheme: toggle,
    onConnect: connectAll,
    onDisconnect: disconnectAll,
    onStart: startExp,
    onStop: stopExp,
  });

  // Native menu → emits 'menu' events from the Rust side
  useEffect(() => {
    if (!isTauri) return;   // native menu only exists in the desktop shell
    const u = listen<string>("menu", (e) => {
      const id = e.payload;
      if (id.startsWith("menu_tab_")) setTab(id.slice("menu_tab_".length));
      else if (id === "menu_theme")      toggle();
      else if (id === "menu_connect")    connectAll();
      else if (id === "menu_disconnect") disconnectAll();
      else if (id === "menu_exp_start")  startExp();
      else if (id === "menu_exp_stop")   stopExp();
      else if (id === "menu_open_data") rpc("results_open_folder").catch(() => {});
    });
    return () => { u.then((fn) => fn()).catch(() => {}); };
  }, [toggle, startExp, stopExp]);

  // Experiment-complete native notification
  const lastRunning = useRef(false);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.experimentState();
        if (!alive) return;
        if (lastRunning.current && !s.running) {
          // running → not-running transition
          const body = s.status?.toLowerCase().includes("error")
            ? `Experiment ended with error: ${s.status}`
            : `Experiment complete · ${s.acq} images captured`;
          try {
            if (isTauri) {
              let allowed = await isPermissionGranted();
              if (!allowed) allowed = (await requestPermission()) === "granted";
              if (allowed) sendNotification({ title: "Digital Holography", body });
            } else if ("Notification" in window) {
              if (Notification.permission === "default") await Notification.requestPermission();
              if (Notification.permission === "granted") new Notification("Digital Holography", { body });
            }
          } catch { /* ignore */ }
        }
        lastRunning.current = s.running;
      } catch { /* ignore */ }
    };
    const id = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const pageTitle = NAV_ITEMS.find((n) => n.id === tab)?.label ?? "";

  return (
    <div className="h-full flex flex-col text-ink font-sans">
      {/* Custom titlebar only in the desktop shell; the browser has its own. */}
      {isTauri && <TitleBar theme={theme} onToggleTheme={toggle} />}

      <div className="flex-1 flex min-h-0">
        <Sidebar active={tab} onSelect={setTab} />

        <main className="flex-1 min-w-0 flex flex-col">
          {/* page header — large title + theme toggle (toggle lives here so it
              exists in the browser, where there's no custom titlebar). */}
          <div className="px-7 pt-5 pb-3 flex items-center justify-between">
            <h1 className="text-[22px] font-bold tracking-[-0.022em] text-ink">
              {pageTitle}
            </h1>
            <button
              type="button"
              onClick={toggle}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
              aria-label="Toggle theme"
              className="grid place-items-center w-8 h-8 rounded-md text-soft hover:text-ink hover:bg-panel transition-colors"
            >
              {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
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

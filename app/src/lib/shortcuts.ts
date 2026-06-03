/* Cross-platform keyboard shortcuts.
   ⌘/Ctrl + 1..6 → tab switch, ⌘/Ctrl + T → theme toggle,
   ⌘/Ctrl + R → start, ⌘/Ctrl + . → stop, etc.
   These fire whether or not the native menu is visible. */

import { useEffect } from "react";

const TAB_KEYS: Record<string, string> = {
  "1": "run",
  "2": "laser",
  "3": "switch",
  "4": "polarization",
  "5": "config",
  "6": "results",
};

export function useShortcuts(handlers: {
  onTab:      (tab: string) => void;
  onTheme?:   () => void;
  onStart?:   () => void;
  onStop?:    () => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      const key = e.key.toLowerCase();
      if (key in TAB_KEYS) {
        e.preventDefault();
        handlers.onTab(TAB_KEYS[key]);
      } else if (key === "t" && handlers.onTheme) {
        e.preventDefault(); handlers.onTheme();
      } else if (key === "r" && handlers.onStart) {
        e.preventDefault(); handlers.onStart();
      } else if (key === "." && handlers.onStop) {
        e.preventDefault(); handlers.onStop();
      } else if (key === "k" && !e.shiftKey && handlers.onConnect) {
        e.preventDefault(); handlers.onConnect();
      } else if (key === "k" &&  e.shiftKey && handlers.onDisconnect) {
        e.preventDefault(); handlers.onDisconnect();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handlers]);
}

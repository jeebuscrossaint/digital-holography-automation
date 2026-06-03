import { Activity, Settings, Sliders, Shuffle, Zap, Play, FileBarChart } from "lucide-react";
import { cn } from "@/lib/utils";
import { ReactNode } from "react";

export const NAV_ITEMS: { id: string; label: string; icon: ReactNode }[] = [
  { id: "run",          label: "Run experiment", icon: <Play         className="h-3.5 w-3.5" /> },
  { id: "laser",        label: "Laser",          icon: <Zap          className="h-3.5 w-3.5" /> },
  { id: "switch",       label: "Switch",         icon: <Shuffle      className="h-3.5 w-3.5" /> },
  { id: "polarization", label: "Polarization",   icon: <Sliders      className="h-3.5 w-3.5" /> },
  { id: "config",       label: "Configuration",  icon: <Settings     className="h-3.5 w-3.5" /> },
  { id: "results",      label: "Results",        icon: <FileBarChart className="h-3.5 w-3.5" /> },
];

export function Sidebar({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside
      className="shrink-0 flex flex-col border-r border-border/60"
      style={{ width: 196, background: "hsl(var(--panel) / 0.55)" }}
    >
      <div className="px-4 pt-4 pb-2">
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-faint">
          Workspace
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 px-2 pb-3">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => onSelect(item.id)}
            className={cn(
              "flex items-center gap-2.5 px-2.5 h-[26px] rounded-md text-[12.5px]",
              "transition-colors text-left",
              active === item.id
                ? "bg-elevated text-ink shadow-[0_0_0_0.5px_hsl(var(--border))]"
                : "text-soft hover:bg-elevated/60 hover:text-ink"
            )}
          >
            <span className={cn(
              active === item.id ? "text-accent" : "text-faint"
            )}>
              {item.icon}
            </span>
            <span className="truncate">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="mt-auto px-4 py-3 border-t border-border/60">
        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-faint">
          <Activity className="h-3 w-3" />
          v0.1.0
        </div>
      </div>
    </aside>
  );
}

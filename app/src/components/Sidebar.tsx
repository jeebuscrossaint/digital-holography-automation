import { Settings, Sliders, Shuffle, Zap, Play, FileBarChart } from "lucide-react";
import { cn } from "@/lib/utils";
import { ReactNode } from "react";

export const NAV_ITEMS: { id: string; label: string; icon: ReactNode }[] = [
  { id: "run",          label: "Run experiment", icon: <Play         className="h-[14px] w-[14px]" /> },
  { id: "laser",        label: "Laser",          icon: <Zap          className="h-[14px] w-[14px]" /> },
  { id: "switch",       label: "Switch",         icon: <Shuffle      className="h-[14px] w-[14px]" /> },
  { id: "polarization", label: "Polarization",   icon: <Sliders      className="h-[14px] w-[14px]" /> },
  { id: "config",       label: "Configuration",  icon: <Settings     className="h-[14px] w-[14px]" /> },
  { id: "results",      label: "Results",        icon: <FileBarChart className="h-[14px] w-[14px]" /> },
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
      className="shrink-0 flex flex-col border-r border-border/70"
      style={{ width: 200, background: "hsl(var(--panel) / 0.7)" }}
    >
      <div className="px-3 pt-3 pb-1.5">
        <div className="px-2 text-[11px] font-semibold text-soft">
          Devices
        </div>
      </div>

      <nav className="flex flex-col gap-px px-2 pb-3">
        {NAV_ITEMS.map((item) => {
          const selected = active === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelect(item.id)}
              className={cn(
                "flex items-center gap-2 px-2 h-[24px] rounded-[5px]",
                "text-[13px] transition-colors text-left",
                selected
                  ? "bg-accent text-white"
                  : "text-ink hover:bg-soft/10"
              )}
            >
              <span className={cn(selected ? "text-white" : "text-faint")}>
                {item.icon}
              </span>
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto px-4 py-2.5 border-t border-border/70">
        <a
          href={`https://github.com/jeebuscrossaint/digital-holography-automation/commit/${__GIT_COMMIT__.replace("-dirty", "")}`}
          target="_blank"
          rel="noreferrer"
          className="text-[11px] text-faint font-mono hover:text-soft"
          title="Open this build's commit on GitHub"
        >
          {__GIT_COMMIT__}
        </a>
      </div>
    </aside>
  );
}

import { useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "./ui/Button";
import { cn } from "@/lib/utils";

export type LogLevel = "INFO" | "OK" | "WARN" | "ERROR" | "DEBUG";
export interface LogEntry {
  ts: string;
  level: LogLevel;
  text: string;
}

const LEVEL_CLASS: Record<LogLevel, string> = {
  INFO:  "text-soft",
  OK:    "text-ok",
  WARN:  "text-warn",
  ERROR: "text-bad",
  DEBUG: "text-faint",
};

export function LogPanel({
  entries,
  onClear,
}: {
  entries: LogEntry[];
  onClear: () => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [entries]);

  return (
    <div className="flex flex-col h-full bg-panel border-l border-border w-[380px]">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-faint">
          Activity
        </span>
        <Button variant="ghost" size="sm" onClick={onClear}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div
        ref={ref}
        className="flex-1 overflow-auto px-4 py-3 font-mono text-[12px] leading-relaxed"
      >
        {entries.length === 0 ? (
          <div className="text-faint italic">no events yet</div>
        ) : (
          entries.map((e, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-faint">[{e.ts}]</span>
              <span className={cn("whitespace-pre-wrap break-words", LEVEL_CLASS[e.level])}>
                {e.text}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

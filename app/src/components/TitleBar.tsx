import { Moon, Sun, Minus, Square, X } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { cn } from "@/lib/utils";

// Resolve the current window lazily inside handlers so any timing weirdness
// at first render can't make these buttons disappear.
const safe = (fn: () => Promise<unknown>) => () => { fn().catch(() => {}); };

export function TitleBar({
  theme,
  onToggleTheme,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}) {
  const onMin   = safe(() => getCurrentWindow().minimize());
  const onMax   = safe(() => getCurrentWindow().toggleMaximize());
  const onClose = safe(() => getCurrentWindow().close());

  return (
    <div
      data-tauri-drag-region
      style={{ height: 36 }}
      className="shrink-0 flex bg-bg border-b border-border select-none"
    >
      <div
        data-tauri-drag-region
        className="flex items-center px-4 gap-2 flex-1 min-w-0"
      >
        <span
          aria-hidden
          className="h-1.5 w-1.5 rounded-full shrink-0"
          style={{ background: "hsl(var(--accent))" }}
        />
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-faint truncate">
          photonic lantern holography
        </span>
      </div>

      <Btn onClick={onToggleTheme} title={theme === "dark" ? "Light mode" : "Dark mode"}>
        {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
      </Btn>
      <span className="self-center mx-0.5 h-4 w-px bg-border/70" />
      <Btn onClick={onMin}   title="Minimize"><Minus  className="h-3.5 w-3.5" /></Btn>
      <Btn onClick={onMax}   title="Maximize"><Square className="h-3   w-3"   /></Btn>
      <Btn onClick={onClose} title="Close" danger><X  className="h-3.5 w-3.5" /></Btn>
    </div>
  );
}

function Btn({
  children,
  danger,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }) {
  return (
    <button
      type="button"
      data-tauri-no-drag
      {...rest}
      style={{ width: 44 }}
      className={cn(
        "shrink-0 flex items-center justify-center text-soft transition-colors",
        danger ? "hover:bg-bad hover:text-white" : "hover:bg-panel hover:text-ink"
      )}
    />
  );
}

import { Moon, Sun, Minus, Maximize2, X } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { cn } from "@/lib/utils";

export function TitleBar({
  theme,
  onToggleTheme,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}) {
  const win = getCurrentWindow();
  return (
    <div
      data-tauri-drag-region
      className="h-10 shrink-0 flex items-stretch border-b border-border bg-bg select-none"
    >
      {/* Left: app mark (drag) */}
      <div
        data-tauri-drag-region
        className="flex items-center px-4 gap-2 text-faint"
      >
        <span
          aria-hidden
          className="h-2 w-2 rounded-full"
          style={{ background: "hsl(var(--accent))" }}
        />
        <span className="font-mono text-[11px] uppercase tracking-wider">
          photonic lantern holography
        </span>
      </div>

      <div data-tauri-drag-region className="flex-1" />

      {/* Theme toggle (no-drag) */}
      <button
        data-tauri-no-drag
        onClick={onToggleTheme}
        className="px-3 grid place-items-center text-faint hover:text-ink hover:bg-panel"
        title={theme === "dark" ? "Switch to light" : "Switch to dark"}
      >
        {theme === "dark" ? (
          <Sun className="h-4 w-4" />
        ) : (
          <Moon className="h-4 w-4" />
        )}
      </button>

      {/* Window controls (no-drag) */}
      <div data-tauri-no-drag className="flex items-stretch">
        <SysButton onClick={() => win.minimize()} title="Minimize">
          <Minus className="h-4 w-4" />
        </SysButton>
        <SysButton onClick={() => win.toggleMaximize()} title="Maximize">
          <Maximize2 className="h-3.5 w-3.5" />
        </SysButton>
        <SysButton onClick={() => win.close()} title="Close" danger>
          <X className="h-4 w-4" />
        </SysButton>
      </div>
    </div>
  );
}

function SysButton({
  children,
  danger,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }) {
  return (
    <button
      {...rest}
      className={cn(
        "h-full w-12 grid place-items-center text-faint transition-colors",
        danger ? "hover:bg-bad hover:text-white" : "hover:bg-panel hover:text-ink"
      )}
    />
  );
}

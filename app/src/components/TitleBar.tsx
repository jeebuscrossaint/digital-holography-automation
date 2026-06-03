import { Moon, Sun, Minus, Square, X } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { cn } from "@/lib/utils";

export function TitleBar({ theme, onToggleTheme }: { theme: "light" | "dark"; onToggleTheme: () => void }) {
  const win = getCurrentWindow();

  return (
    <div
      data-tauri-drag-region
      className="h-9 flex items-center px-3 bg-bg border-b border-border select-none"
    >
      <div className="font-mono text-[11px] tracking-wider uppercase text-faint">
        photonic lantern holography
      </div>
      <div className="flex-1" />

      <button
        data-tauri-no-drag
        onClick={onToggleTheme}
        className="h-7 w-7 grid place-items-center rounded text-faint hover:text-ink hover:bg-panel"
        title={theme === "dark" ? "Light mode" : "Dark mode"}
      >
        {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
      </button>

      <div className="w-3" />

      <div data-tauri-no-drag className="flex items-center gap-0.5">
        <WinBtn onClick={() => win.minimize()} title="Minimize">
          <Minus className="h-3 w-3" />
        </WinBtn>
        <WinBtn onClick={() => win.toggleMaximize()} title="Maximize">
          <Square className="h-3 w-3" />
        </WinBtn>
        <WinBtn onClick={() => win.close()} title="Close" danger>
          <X className="h-3 w-3" />
        </WinBtn>
      </div>
    </div>
  );
}

function WinBtn({
  children,
  danger,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }) {
  return (
    <button
      {...rest}
      className={cn(
        "h-7 w-9 grid place-items-center rounded text-faint",
        danger ? "hover:bg-bad hover:text-white" : "hover:bg-panel hover:text-ink"
      )}
    />
  );
}

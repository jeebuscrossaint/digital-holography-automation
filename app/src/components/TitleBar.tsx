import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";

const safe = (fn: () => Promise<unknown>) => () => { fn().catch(() => {}); };

export function TitleBar({
  theme,
  onToggleTheme,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}) {
  return (
    <div
      data-tauri-drag-region
      style={{
        height: 36,
        display: "flex",
        background: "hsl(var(--bg))",
        borderBottom: "1px solid hsl(var(--border))",
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      <div
        data-tauri-drag-region
        style={{
          flex: 1, display: "flex", alignItems: "center",
          padding: "0 16px", gap: 8, minWidth: 0,
        }}
      >
        <span
          aria-hidden
          style={{
            width: 6, height: 6, borderRadius: 999,
            background: "hsl(var(--accent))", flexShrink: 0,
          }}
        />
        <span
          style={{
            fontFamily: "ui-monospace, 'Cascadia Mono', 'JetBrains Mono', monospace",
            fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase",
            color: "hsl(var(--faint))",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}
        >
          photonic lantern holography
        </span>
      </div>

      <Ctrl onClick={onToggleTheme} title={theme === "dark" ? "Light mode" : "Dark mode"}>
        {theme === "dark"
          ? <Sun  style={{ width: 14, height: 14 }} />
          : <Moon style={{ width: 14, height: 14 }} />}
      </Ctrl>

      <span style={{
        alignSelf: "center", margin: "0 2px",
        height: 16, width: 1, background: "hsl(var(--border))",
      }} />

      <Ctrl onClick={safe(() => getCurrentWindow().minimize())} title="Minimize">
        <Glyph>{"−"}</Glyph>{/* − minus sign */}
      </Ctrl>
      <Ctrl onClick={safe(() => getCurrentWindow().toggleMaximize())} title="Maximize">
        <Glyph size={11}>{"□"}</Glyph>{/* □ white square */}
      </Ctrl>
      <Ctrl onClick={safe(() => getCurrentWindow().close())} title="Close" danger>
        <Glyph>{"×"}</Glyph>{/* × multiplication sign */}
      </Ctrl>
    </div>
  );
}

function Ctrl({
  children, onClick, title, danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  danger?: boolean;
}) {
  const [hover, setHover] = useState(false);
  return (
    <button
      type="button"
      data-tauri-no-drag
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={title}
      aria-label={title}
      style={{
        width: 44, height: 36,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: hover
          ? (danger ? "hsl(var(--bad))" : "hsl(var(--panel))")
          : "transparent",
        color: hover
          ? (danger ? "#fff" : "hsl(var(--ink))")
          : "hsl(var(--soft))",
        border: 0,
        padding: 0,
        cursor: "default",
        transition: "background 80ms, color 80ms",
      }}
    >
      {children}
    </button>
  );
}

function Glyph({ children, size = 14 }: { children: React.ReactNode; size?: number }) {
  return (
    <span
      aria-hidden
      style={{
        fontSize: size,
        lineHeight: 1,
        fontFamily: "system-ui, 'Segoe UI', sans-serif",
      }}
    >
      {children}
    </span>
  );
}

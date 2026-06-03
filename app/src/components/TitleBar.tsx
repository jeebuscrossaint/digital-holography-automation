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
        height: 32,
        display: "flex",
        alignItems: "center",
        background: "hsl(var(--bg))",
        borderBottom: "1px solid hsl(var(--border))",
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      {/* macOS traffic lights — top-left */}
      <div
        data-tauri-no-drag
        className="group"
        style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "0 14px", height: "100%",
        }}
      >
        <Light
          base="#ff5f57"
          hover="#ec4034"
          ring="#e0443e"
          glyph="×"
          onClick={safe(() => getCurrentWindow().close())}
          title="Close"
        />
        <Light
          base="#febc2e"
          hover="#dba01b"
          ring="#dea123"
          glyph={"−"}    /* − minus */
          onClick={safe(() => getCurrentWindow().minimize())}
          title="Minimize"
        />
        <Light
          base="#28c840"
          hover="#1aab30"
          ring="#1ba328"
          glyph="+"
          onClick={safe(() => getCurrentWindow().toggleMaximize())}
          title="Maximize"
        />
      </div>

      {/* Centered app label (drag region) */}
      <div
        data-tauri-drag-region
        style={{
          flex: 1, display: "flex", justifyContent: "center", alignItems: "center",
          minWidth: 0, height: "100%",
        }}
      >
        <span
          style={{
            fontFamily: "ui-sans-serif, -apple-system, 'SF Pro Text', 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif",
            fontSize: 12, fontWeight: 600, letterSpacing: "-0.01em",
            color: "hsl(var(--soft))",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}
        >
          Digital Holography
        </span>
      </div>

      {/* Right side: theme toggle */}
      <div data-tauri-no-drag style={{ display: "flex", alignItems: "center", padding: "0 10px", height: "100%" }}>
        <button
          type="button"
          onClick={onToggleTheme}
          title={theme === "dark" ? "Light mode" : "Dark mode"}
          aria-label="Toggle theme"
          style={{
            width: 28, height: 22, border: 0, padding: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "transparent", color: "hsl(var(--soft))",
            borderRadius: 6, cursor: "default",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "hsl(var(--panel))"; (e.currentTarget as HTMLElement).style.color = "hsl(var(--ink))"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = "hsl(var(--soft))"; }}
        >
          {theme === "dark"
            ? <Sun  style={{ width: 13, height: 13 }} />
            : <Moon style={{ width: 13, height: 13 }} />}
        </button>
      </div>
    </div>
  );
}

function Light({
  base, hover, ring, glyph, onClick, title,
}: {
  base: string;
  hover: string;
  ring: string;
  glyph: string;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className="traffic-light"
      style={{
        width: 12, height: 12,
        borderRadius: "50%",
        background: base,
        border: `0.5px solid ${ring}`,
        padding: 0, cursor: "default",
        display: "flex", alignItems: "center", justifyContent: "center",
        boxShadow: "0 0.5px 0 rgba(255,255,255,0.18) inset",
        transition: "background 90ms ease",
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = hover; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = base; }}
    >
      {/* Glyph: invisible by default, fade in when ANY of the three is hovered */}
      <span
        aria-hidden
        className="traffic-glyph"
        style={{
          fontFamily: "ui-sans-serif, -apple-system, 'SF Pro Text', 'Segoe UI', sans-serif",
          fontSize: 9, lineHeight: 1, fontWeight: 700,
          color: "rgba(0,0,0,0.55)",
          opacity: 0, transition: "opacity 80ms ease",
          marginTop: -0.5,
        }}
      >
        {glyph}
      </span>
    </button>
  );
}

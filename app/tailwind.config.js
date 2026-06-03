/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Text"',
          '"Segoe UI Variable Text"',
          '"Segoe UI"',
          "Inter",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          '"SF Mono"',
          '"JetBrains Mono"',
          '"Cascadia Mono"',
          '"Consolas"',
          "monospace",
        ],
      },
      colors: {
        // semantic surfaces (driven by CSS vars in index.css so dark mode just flips)
        bg:       "hsl(var(--bg) / <alpha-value>)",
        panel:    "hsl(var(--panel) / <alpha-value>)",
        elevated: "hsl(var(--elevated) / <alpha-value>)",
        border:   "hsl(var(--border) / <alpha-value>)",
        ink:      "hsl(var(--ink) / <alpha-value>)",
        soft:     "hsl(var(--soft) / <alpha-value>)",
        faint:    "hsl(var(--faint) / <alpha-value>)",
        accent:   "hsl(var(--accent) / <alpha-value>)",
        ok:       "hsl(var(--ok) / <alpha-value>)",
        warn:     "hsl(var(--warn) / <alpha-value>)",
        bad:      "hsl(var(--bad) / <alpha-value>)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};

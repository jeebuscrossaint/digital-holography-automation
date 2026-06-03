import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function gitShortSha(): string {
  try {
    return execSync("git rev-parse --short HEAD", { cwd: __dirname })
      .toString().trim();
  } catch {
    return "unknown";
  }
}
function gitDirty(): boolean {
  try {
    return execSync("git status --porcelain", { cwd: __dirname })
      .toString().trim().length > 0;
  } catch {
    return false;
  }
}

const COMMIT = gitShortSha() + (gitDirty() ? "-dirty" : "");

// Tauri expects a fixed port and to be able to embed the dev server output.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    // Stop the Vite file watcher from following Cargo's output directory.
    // Without this it EBUSY-crashes whenever cargo overwrites the DLL.
    watch: {
      ignored: [
        "**/src-tauri/target/**",
        "**/src-tauri/gen/**",
      ],
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
  define: {
    __GIT_COMMIT__: JSON.stringify(COMMIT),
  },
  build: {
    target: "esnext",
    sourcemap: false,
  },
});

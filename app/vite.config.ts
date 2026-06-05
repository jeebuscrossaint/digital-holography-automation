import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function gitShortSha(): string {
  // Read the SHA straight from .git so it works even when the `git` binary
  // isn't on PATH (common on freshly-set-up Windows machines — otherwise this
  // showed "unknown").
  try {
    const gitDir = path.join(__dirname, "..", ".git");
    let head = fs.readFileSync(path.join(gitDir, "HEAD"), "utf8").trim();
    if (head.startsWith("ref:")) {
      const ref = head.slice(4).trim();
      const refPath = path.join(gitDir, ref);
      if (fs.existsSync(refPath)) {
        head = fs.readFileSync(refPath, "utf8").trim();
      } else {
        const packed = fs.readFileSync(path.join(gitDir, "packed-refs"), "utf8");
        const line = packed.split("\n").find((l) => l.trim().endsWith(ref));
        if (line) head = line.split(" ")[0];
      }
    }
    if (/^[0-9a-f]{7,40}$/.test(head)) return head.slice(0, 7);
  } catch { /* fall through to git binary */ }
  try {
    return execSync("git rev-parse --short HEAD", { cwd: __dirname }).toString().trim();
  } catch {
    return "dev";
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

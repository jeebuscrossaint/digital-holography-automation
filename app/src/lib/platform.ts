// True when running inside the Tauri desktop shell; false in a plain browser
// (the web-app / Tailscale deployment). Used to gate native-only features.
export const isTauri =
  typeof window !== "undefined" &&
  ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// Suppress WebView2's "Refresh / Inspect Element" context menu so the
// app feels native. Inputs / textareas keep their menus (text editing).
window.addEventListener("contextmenu", (e) => {
  const target = e.target as HTMLElement | null;
  const editable = target?.closest("input, textarea, [contenteditable='true']");
  if (!editable) e.preventDefault();
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

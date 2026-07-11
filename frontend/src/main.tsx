import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Required once for Astryx styling (frontend/AGENTS.md + pre-built neutral theme).
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@astryxdesign/theme-neutral/theme.css";

import { App } from "./app/App";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error('Root element "#root" was not found');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendRoot, "..");

/** Exact public key published to the client. Never a startsWith allowlist alone. */
const APPROVED_PUBLIC_ENV_KEY = "VITE_API_BASE_URL";

/**
 * Vite `envPrefix` is startsWith-only and cannot exact-match a single key
 * (e.g. `VITE_API_BASE_URL` would still publish `VITE_API_BASE_URL_SECRET`).
 * Use a sentinel that never matches real env names so auto-injection is empty,
 * then publish only the approved key via `define`.
 */
const NON_MATCHING_ENV_PREFIX = "__JOBAGENT_NO_AUTO_PUBLIC_ENV__";

// Load root env for the approved key only; envDir stays at repository root (no nested .env).
export default defineConfig(({ mode }) => {
  // Prefix filter may return sibling keys; only the exact approved key is published.
  const candidates = loadEnv(mode, repoRoot, APPROVED_PUBLIC_ENV_KEY);
  const approvedValue = candidates[APPROVED_PUBLIC_ENV_KEY] ?? "";

  return {
    plugins: [react()],
    envDir: repoRoot,
    envPrefix: [NON_MATCHING_ENV_PREFIX],
    define: {
      [`import.meta.env.${APPROVED_PUBLIC_ENV_KEY}`]: JSON.stringify(approvedValue),
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
    },
    preview: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      globals: true,
      css: true,
    },
  };
});

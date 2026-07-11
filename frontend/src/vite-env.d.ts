/// <reference types="vite/client" />

/**
 * Public frontend environment contract.
 * Exact-key publication only: VITE_API_BASE_URL (not a startsWith envPrefix).
 * Backend-only names must never appear here.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

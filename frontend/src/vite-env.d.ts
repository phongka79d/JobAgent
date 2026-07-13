/// <reference types="vite/client" />

/**
 * Frontend runtime may read only VITE_API_BASE_URL.
 * No nested frontend .env; Compose/root env injects this name for the client.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

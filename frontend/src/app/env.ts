/**
 * Typed access to the only public frontend configuration value.
 * Backend-only variables (Neo4j, ShopAIKey, SQLite, files paths) must never be read here.
 *
 * Vite publishes only `VITE_API_BASE_URL` via exact-key `define` (not envPrefix startsWith).
 * Never pass or serialize the whole `import.meta.env` object. Read only the approved key.
 */

export interface PublicConfig {
  readonly apiBaseUrl: string;
}

const DEFAULT_API_BASE_URL = "http://localhost:8000";

/** Narrow public env surface: only the allowlisted Vite key. */
export type PublicEnvInput = Pick<ImportMetaEnv, "VITE_API_BASE_URL">;

function approvedPublicEnv(): PublicEnvInput {
  // Property access only; do not pass `import.meta.env` as a whole object.
  return {
    VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  };
}

export function readPublicConfig(env: PublicEnvInput = approvedPublicEnv()): PublicConfig {
  const raw = env.VITE_API_BASE_URL;
  if (typeof raw === "string" && raw.trim().length > 0) {
    return { apiBaseUrl: raw.trim() };
  }
  return { apiBaseUrl: DEFAULT_API_BASE_URL };
}

/**
 * Shared FastAPI HTTP helpers for chat and profile clients.
 * Base URL comes only from `readPublicConfig().apiBaseUrl` (VITE_API_BASE_URL).
 */

import { readPublicConfig } from "../app/env";

export class HttpApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message?: string) {
    super(message ?? code);
    this.name = "HttpApiError";
    this.status = status;
    this.code = code;
  }
}

export function resolveBaseUrl(override?: string): string {
  const raw = override ?? readPublicConfig().apiBaseUrl;
  return raw.replace(/\/+$/, "");
}

export function joinUrl(baseUrl: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Read a stable failure code from FastAPI envelopes.
 * Supports `detail` as a string or `{ code: string }` (Plan 4 attachment/profile).
 */
export async function readErrorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string" && detail.length > 0) {
        return detail;
      }
      if (
        typeof detail === "object" &&
        detail !== null &&
        "code" in detail &&
        typeof (detail as { code: unknown }).code === "string" &&
        (detail as { code: string }).code.length > 0
      ) {
        return (detail as { code: string }).code;
      }
    }
  } catch {
    // ignore non-JSON error bodies
  }
  return `http_${response.status}`;
}

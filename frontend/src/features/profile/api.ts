/**
 * Typed profile read + shared CV upload client.
 * Sidebar and chat composer must import these — do not duplicate multipart/base URL logic.
 */

import {
  HttpApiError,
  joinUrl,
  readErrorCode,
  resolveBaseUrl,
} from "../../lib/http";
import {
  PROFILE_API_PATHS,
  parseProfileResponse,
  parseStagedAttachmentResponse,
  type ProfileResponse,
  type StagedAttachmentResponse,
} from "./contracts";

export class ProfileApiError extends HttpApiError {
  constructor(status: number, code: string, message?: string) {
    super(status, code, message);
    this.name = "ProfileApiError";
  }
}

export interface ProfileRequestOptions {
  readonly signal?: AbortSignal;
  readonly baseUrl?: string;
  readonly fetchImpl?: typeof fetch;
}

export interface UploadCvOptions extends ProfileRequestOptions {
  /** Multipart field name expected by POST /api/attachments/cv. */
  readonly fieldName?: string;
}

/**
 * GET /api/profile — approved profile presence + safe active attachment metadata.
 */
export async function fetchProfile(
  options: ProfileRequestOptions = {},
): Promise<ProfileResponse> {
  const baseUrl = resolveBaseUrl(options.baseUrl);
  const fetchImpl = options.fetchImpl ?? fetch;
  const url = joinUrl(baseUrl, PROFILE_API_PATHS.profile);

  const response = await fetchImpl(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });

  if (!response.ok) {
    const code = await readErrorCode(response);
    throw new ProfileApiError(response.status, code);
  }

  const json: unknown = await response.json();
  return parseProfileResponse(json);
}

/**
 * POST /api/attachments/cv — one shared multipart upload for sidebar and chat.
 * Never reads store/provider; returns only sanitized staged/active metadata.
 */
export async function uploadCv(
  file: File,
  options: UploadCvOptions = {},
): Promise<StagedAttachmentResponse> {
  const baseUrl = resolveBaseUrl(options.baseUrl);
  const fetchImpl = options.fetchImpl ?? fetch;
  const url = joinUrl(baseUrl, PROFILE_API_PATHS.upload);
  const fieldName = options.fieldName ?? "file";

  const body = new FormData();
  body.append(fieldName, file, file.name);

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      // Let the runtime set multipart boundary; do not set Content-Type manually.
      headers: { Accept: "application/json" },
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (
      options.signal?.aborted ||
      (error instanceof DOMException && error.name === "AbortError")
    ) {
      throw error;
    }
    throw error;
  }

  if (!response.ok) {
    const code = await readErrorCode(response);
    throw new ProfileApiError(response.status, code);
  }

  const json: unknown = await response.json();
  return parseStagedAttachmentResponse(json);
}

/**
 * Safe absolute URL for GET /api/profile/cv (view/download active PDF).
 * Bytes are never fetched here — callers use the URL as a link target only.
 */
export function activeCvUrl(baseUrl?: string): string {
  return joinUrl(resolveBaseUrl(baseUrl), PROFILE_API_PATHS.cv);
}

export function profileUrl(baseUrl?: string): string {
  return joinUrl(resolveBaseUrl(baseUrl), PROFILE_API_PATHS.profile);
}

export function uploadCvUrl(baseUrl?: string): string {
  return joinUrl(resolveBaseUrl(baseUrl), PROFILE_API_PATHS.upload);
}

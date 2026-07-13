/**
 * Typed profile / CV transport (Plan 4 §7.8).
 * Uses only VITE_API_BASE_URL via the shared chat API origin helpers.
 * Never stores or returns raw PDF bytes or storage_path.
 */

import {
  apiUrl,
  ChatApiError,
  parseErrorBody,
} from '../../lib/api/chat';
import {
  parseCvUploadResponse,
  parseProfileReadResponse,
  type CvUploadResponse,
  type ProfileReadResponse,
} from './types';

export {ChatApiError};

/** GET /api/profile → empty or active profile + attachment metadata. */
export async function fetchProfile(
  signal?: AbortSignal,
): Promise<ProfileReadResponse> {
  const response = await fetch(apiUrl('/api/profile'), {
    method: 'GET',
    headers: {Accept: 'application/json'},
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    throw parseErrorBody(response.status, text);
  }
  let json: unknown;
  try {
    json = JSON.parse(text) as unknown;
  } catch {
    throw new ChatApiError(
      response.status,
      'INVALID_JSON',
      'Profile body is not JSON',
    );
  }
  try {
    return parseProfileReadResponse(json);
  } catch (err) {
    throw new ChatApiError(
      response.status,
      'INVALID_PROFILE_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid profile payload',
    );
  }
}

/**
 * POST /api/attachments/cv — shared by sidebar and chat composer.
 * Multipart field name is ``file`` (backend UploadFile dependency).
 */
export async function uploadCv(
  file: File,
  signal?: AbortSignal,
): Promise<CvUploadResponse> {
  const form = new FormData();
  form.append('file', file, file.name);

  const response = await fetch(apiUrl('/api/attachments/cv'), {
    method: 'POST',
    headers: {Accept: 'application/json'},
    body: form,
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    throw parseErrorBody(response.status, text);
  }
  let json: unknown;
  try {
    json = JSON.parse(text) as unknown;
  } catch {
    throw new ChatApiError(
      response.status,
      'INVALID_JSON',
      'CV upload body is not JSON',
    );
  }
  try {
    return parseCvUploadResponse(json);
  } catch (err) {
    throw new ChatApiError(
      response.status,
      'INVALID_UPLOAD_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid CV upload payload',
    );
  }
}

/**
 * Absolute URL for GET /api/profile/cv (view/download only).
 * Callers open this URL; raw PDF bytes never enter React state.
 */
export function getActiveCvUrl(): string {
  return apiUrl('/api/profile/cv');
}

/** Concise user intent used after a successful sidebar CV upload turn. */
export const SIDEBAR_CV_TURN_MESSAGE =
  'I uploaded my CV. Please process the attached PDF.';

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
  parseProfileUploadConflict,
  type CvUploadResponse,
  type ProfileUploadConflict,
  type ProfileReadResponse,
} from './types';
import {
  parseConversationDeleteResponse,
  parseConversationListResponse,
  parseConversationMutationResponse,
  parseProfileDeleteResponse,
  parseProfileDetail,
  parseProfileListResponse,
  parseSelectionResponse,
  type ConversationDeleteResponse,
  type ConversationListResponse,
  type ConversationMutationResponse,
  type ProfileDeleteResponse,
  type ProfileDetail,
  type ProfileListResponse,
  type SelectionResponse,
} from './conversationTypes';

export {ChatApiError};

export function getProfileUploadConflict(error: unknown): ProfileUploadConflict | null {
  if (!(error instanceof ChatApiError) || error.status !== 409) return null;
  try {
    return parseProfileUploadConflict(error.detail);
  } catch {
    return null;
  }
}

/** GET /api/profile → empty or active profile + attachment metadata. */
export async function fetchActiveProfileCompat(
  signal?: AbortSignal,
): Promise<ProfileReadResponse> {
  const response = await fetch(apiUrl('/api/profile'), {
    method: 'GET',
    headers: {Accept: 'application/json'},
    signal,
    cache: 'no-store',
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

async function jsonRequest<T>(
  path: string,
  init: RequestInit,
  parse: (value: unknown) => T,
): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  const text = await response.text();
  if (!response.ok) throw parseErrorBody(response.status, text);
  try {
    return parse(JSON.parse(text) as unknown);
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError(response.status, 'INVALID_PROFILE_PAYLOAD', error instanceof Error ? error.message : 'Invalid profile payload');
  }
}

const jsonHeaders = {'Content-Type': 'application/json', Accept: 'application/json'};
const profilePath = (profileId: string) => `/api/profiles/${encodeURIComponent(profileId)}`;

export function fetchProfiles(signal?: AbortSignal): Promise<ProfileListResponse> {
  return jsonRequest('/api/profiles', {method: 'GET', headers: {Accept: 'application/json'}, signal, cache: 'no-store'}, parseProfileListResponse);
}
export function fetchProfile(profileId: string, signal?: AbortSignal): Promise<ProfileDetail> {
  return jsonRequest(profilePath(profileId), {method: 'GET', headers: {Accept: 'application/json'}, signal}, parseProfileDetail);
}
export function updateProfile(profileId: string, displayName: string, signal?: AbortSignal): Promise<ProfileDetail> {
  return jsonRequest(profilePath(profileId), {method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({display_name: displayName}), signal}, parseProfileDetail);
}
export function activateProfile(profileId: string, signal?: AbortSignal): Promise<SelectionResponse> {
  return jsonRequest(`${profilePath(profileId)}/activate`, {method: 'POST', headers: {Accept: 'application/json'}, signal}, parseSelectionResponse);
}
export function deleteProfile(profileId: string, signal?: AbortSignal): Promise<ProfileDeleteResponse> {
  return jsonRequest(profilePath(profileId), {method: 'DELETE', headers: {Accept: 'application/json'}, signal}, parseProfileDeleteResponse);
}
export function fetchProfileConversations(profileId: string, query: {limit?: number; before?: string | null} = {}, signal?: AbortSignal): Promise<ConversationListResponse> {
  const params = new URLSearchParams(); if (query.limit !== undefined) params.set('limit', String(query.limit)); if (query.before) params.set('before', query.before);
  const suffix = params.size ? `?${params}` : '';
  return jsonRequest(`${profilePath(profileId)}/conversations${suffix}`, {method: 'GET', headers: {Accept: 'application/json'}, signal, cache: 'no-store'}, parseConversationListResponse);
}
export function createProfileConversation(profileId: string, signal?: AbortSignal): Promise<ConversationMutationResponse> {
  return jsonRequest(`${profilePath(profileId)}/conversations`, {method: 'POST', headers: {Accept: 'application/json'}, signal}, parseConversationMutationResponse);
}
export function selectConversation(conversationId: string, signal?: AbortSignal): Promise<ConversationMutationResponse> {
  return jsonRequest(`/api/conversations/${encodeURIComponent(conversationId)}/select`, {method: 'POST', headers: {Accept: 'application/json'}, signal}, parseConversationMutationResponse);
}
export function deleteConversation(conversationId: string, signal?: AbortSignal): Promise<ConversationDeleteResponse> {
  return jsonRequest(`/api/conversations/${encodeURIComponent(conversationId)}`, {method: 'DELETE', headers: {Accept: 'application/json'}, signal}, parseConversationDeleteResponse);
}

export const defaultProfileApi = {fetchProfiles, fetchProfile, updateProfile, activateProfile, deleteProfile, fetchProfileConversations, createProfileConversation, selectConversation, deleteConversation};

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

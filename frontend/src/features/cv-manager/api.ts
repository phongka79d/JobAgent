import {apiUrl, ChatApiError, parseErrorBody} from '../../lib/api/chat';
import {IncrementalSseParser, type SseWireFrame} from '../../lib/sse/parser';
import {
  parseCvManagerListResponse,
  parseProfileReextractApproval,
  parseProfileReextractEvent,
  parseProfileReextractReview,
  type CvManagerListResponse,
  type ProfileReextractApprovalResponse,
  type ProfileReextractEvent,
  type ProfileReextractReview,
} from './types';

export async function fetchCvManager(signal?: AbortSignal): Promise<CvManagerListResponse> {
  const response = await fetch(apiUrl('/api/cvs'), {method: 'GET', headers: {Accept: 'application/json'}, signal});
  const body = await response.text();
  if (!response.ok) throw parseErrorBody(response.status, body);
  try {
    return parseCvManagerListResponse(JSON.parse(body) as unknown);
  } catch {
    throw new ChatApiError(200, 'INVALID_CV_MANAGER_PAYLOAD', 'CV manager data is unavailable');
  }
}

export async function deleteCv(id: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(apiUrl(`/api/cvs/${encodeURIComponent(id)}`), {method: 'DELETE', headers: {Accept: 'application/json'}, signal});
  if (response.status === 204) return;
  throw parseErrorBody(response.status, await response.text());
}

export function cvFileUrl(id: string, disposition: 'inline' | 'attachment'): string {
  return apiUrl(`/api/cvs/${encodeURIComponent(id)}/file?disposition=${disposition}`);
}

async function parsedJson<T>(response: Response, parser: (raw: unknown) => T): Promise<T> {
  const body = await response.text();
  if (!response.ok) throw parseErrorBody(response.status, body);
  try {
    return parser(JSON.parse(body) as unknown);
  } catch {
    throw new ChatApiError(response.status, 'INVALID_PROFILE_REEXTRACT_PAYLOAD', 'Profile review data is unavailable');
  }
}

function parseProfileFrame(frame: SseWireFrame): ProfileReextractEvent {
  const event = parseProfileReextractEvent(JSON.parse(frame.data) as unknown);
  if (frame.event !== null && frame.event !== event.event) throw new Error('SSE event name mismatch');
  if (frame.id !== null && frame.id.toLowerCase() !== event.event_id) throw new Error('SSE event id mismatch');
  return event;
}

export type ProfileReextractStreamHandlers = {
  onEvent: (event: ProfileReextractEvent) => void;
  onMalformed?: (error: Error) => void;
  onDisconnected?: () => void;
};

export async function streamProfileReextract(profileId: string, handlers: ProfileReextractStreamHandlers, signal?: AbortSignal): Promise<void> {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/reextract`), {
    method: 'POST', headers: {Accept: 'text/event-stream', 'Content-Type': 'application/json'}, body: '{}', signal,
  });
  if (!response.ok) throw parseErrorBody(response.status, await response.text());
  if (!response.body) { handlers.onDisconnected?.(); return; }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new IncrementalSseParser();
  let terminal = false;
  const consume = (frames: SseWireFrame[]) => {
    for (const frame of frames) {
      try {
        const event = parseProfileFrame(frame);
        terminal ||= event.event === 'reextract_review_ready' || event.event === 'reextract_failed';
        handlers.onEvent(event);
      } catch (error) {
        handlers.onMalformed?.(error instanceof Error ? error : new Error('Invalid profile re-extract event'));
      }
    }
  };
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) { consume(parser.flush()); break; }
      consume(parser.feed(decoder.decode(value, {stream: true})));
    }
  } finally {
    if (!terminal && !signal?.aborted) handlers.onDisconnected?.();
  }
}

export async function getProfileReextractReview(profileId: string, signal?: AbortSignal): Promise<ProfileReextractReview> {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/reextract-draft`), {method: 'GET', headers: {Accept: 'application/json'}, signal});
  return parsedJson(response, parseProfileReextractReview);
}

export async function approveProfileReextractReview(profileId: string, revision: string, signal?: AbortSignal): Promise<ProfileReextractApprovalResponse> {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/reextract-draft/approve`), {method: 'POST', headers: {Accept: 'application/json', 'Content-Type': 'application/json'}, body: JSON.stringify({revision}), signal});
  return parsedJson(response, parseProfileReextractApproval);
}

export async function discardProfileReextractReview(profileId: string, revision: string, signal?: AbortSignal): Promise<void> {
  const params = new URLSearchParams({revision});
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/reextract-draft?${params}`), {method: 'DELETE', headers: {Accept: 'application/json'}, signal});
  if (response.status === 204) return;
  throw parseErrorBody(response.status, await response.text());
}

export type CvManagerApi = {
  fetchCvManager: typeof fetchCvManager;
  deleteCv: typeof deleteCv;
  streamProfileReextract?: typeof streamProfileReextract;
  getProfileReextractReview?: typeof getProfileReextractReview;
  approveProfileReextractReview?: typeof approveProfileReextractReview;
  discardProfileReextractReview?: typeof discardProfileReextractReview;
};
export const defaultCvManagerApi: Required<CvManagerApi> = {fetchCvManager, deleteCv, streamProfileReextract, getProfileReextractReview, approveProfileReextractReview, discardProfileReextractReview};

import {
  ChatApiError,
  apiUrl,
  parseErrorBody,
} from '../../lib/api/chat';
import {
  consumeTypedSseResponse,
  StreamHttpError,
  type TypedStreamHandlers,
} from '../../lib/sse/stream';
import {isUuidV4} from '../chat/types';
import {
  CV_TAILORING_SESSION_HEADER,
  asTailoringErrorCode,
  parseTailoringDelete,
  parseTailoringSessionDetail,
  parseTailoringSessionList,
  parseTailoringMutationResponse,
  parseTailoringSseFrame,
  type CreateTailoringAiVersionRequest,
  type CreateTailoringManualVersionRequest,
  type CreateTailoringSessionRequest,
  type TailoringDeleteResponse,
  type TailoringSessionDetailResponse,
  type TailoringSessionListResponse,
  type TailoringSseEvent,
  type TailoringVersionMutationResponse,
} from './types';

export type TailoringStreamCallbacks = TypedStreamHandlers<TailoringSseEvent>;

function safeError(status: number, body: string): ChatApiError {
  const parsed = parseErrorBody(status, body);
  const code = asTailoringErrorCode(parsed.code);
  if (code !== null) return new ChatApiError(status, code, parsed.summary);
  return new ChatApiError(status, 'HTTP_ERROR', 'CV tailoring request failed');
}

async function consume(
  response: Response,
  callbacks: TailoringStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  try {
    await consumeTypedSseResponse(
      response,
      {
        onEvent: callbacks.onEvent,
        onMalformed: callbacks.onMalformed,
        onDisconnected: callbacks.onDisconnected,
        onHttpError: (status, body) => {
          throw safeError(status, body);
        },
      },
      parseTailoringSseFrame,
      (event) => event.event === 'run_completed' || event.event === 'run_failed',
      signal,
    );
  } catch (error) {
    if (error instanceof StreamHttpError) {
      throw safeError(error.status, error.body);
    }
    throw error;
  }
}

function requireUuid(value: string, label: string): string {
  if (!isUuidV4(value)) {
    throw new ChatApiError(0, 'INVALID_UUID', `${label} is invalid`);
  }
  return value.toLowerCase();
}

async function jsonRequest(path: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body === undefined ? {} : {'Content-Type': 'application/json'}),
      ...init.headers,
    },
  });
  const body = await response.text();
  if (!response.ok) throw safeError(response.status, body);
  try {
    return JSON.parse(body) as unknown;
  } catch {
    throw new ChatApiError(
      response.status,
      'INVALID_JSON',
      'CV tailoring response is invalid',
    );
  }
}

export async function fetchTailoringSessions(
  signal?: AbortSignal,
): Promise<TailoringSessionListResponse> {
  return parseTailoringSessionList(
    await jsonRequest('/api/cv-tailoring/sessions', {method: 'GET', signal}),
  );
}

export async function fetchTailoringSession(
  sessionId: string,
  versionId?: string | null,
  signal?: AbortSignal,
): Promise<TailoringSessionDetailResponse> {
  const session = requireUuid(sessionId, 'session_id');
  const query = versionId
    ? `?version_id=${encodeURIComponent(requireUuid(versionId, 'version_id'))}`
    : '';
  return parseTailoringSessionDetail(
    await jsonRequest(
      `/api/cv-tailoring/sessions/${encodeURIComponent(session)}${query}`,
      {method: 'GET', signal},
    ),
  );
}

export async function createTailoringManualVersion(
  sessionId: string,
  body: CreateTailoringManualVersionRequest,
  signal?: AbortSignal,
): Promise<TailoringVersionMutationResponse> {
  const session = requireUuid(sessionId, 'session_id');
  return parseTailoringMutationResponse(
    await jsonRequest(
      `/api/cv-tailoring/sessions/${encodeURIComponent(session)}/manual-versions`,
      {method: 'POST', body: JSON.stringify(body), signal},
    ),
  );
}

export async function deleteTailoringSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<TailoringDeleteResponse> {
  const session = requireUuid(sessionId, 'session_id');
  return parseTailoringDelete(
    await jsonRequest(
      `/api/cv-tailoring/sessions/${encodeURIComponent(session)}`,
      {method: 'DELETE', signal},
    ),
  );
}

export async function streamCreateTailoringSession(
  body: CreateTailoringSessionRequest,
  callbacks: TailoringStreamCallbacks & {onSessionId: (sessionId: string) => void},
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl('/api/cv-tailoring/sessions'), {
    method: 'POST',
    headers: {Accept: 'text/event-stream', 'Content-Type': 'application/json'},
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw safeError(response.status, await response.text());
  }
  const header = response.headers.get(CV_TAILORING_SESSION_HEADER);
  if (header === null || !isUuidV4(header)) {
    throw new ChatApiError(
      response.status,
      'INVALID_TAILORING_SESSION_HEADER',
      'CV tailoring session header is invalid',
    );
  }
  callbacks.onSessionId(header.toLowerCase());
  await consume(response, callbacks, signal);
}

export async function streamCreateTailoringAiVersion(
  sessionId: string,
  body: CreateTailoringAiVersionRequest,
  callbacks: TailoringStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const session = requireUuid(sessionId, 'session_id');
  const response = await fetch(
    apiUrl(
      `/api/cv-tailoring/sessions/${encodeURIComponent(session)}/ai-versions`,
    ),
    {
      method: 'POST',
      headers: {Accept: 'text/event-stream', 'Content-Type': 'application/json'},
      body: JSON.stringify(body),
      signal,
    },
  );
  await consume(response, callbacks, signal);
}

export function tailoringSourceUrl(versionId: string): string {
  return apiUrl(
    `/api/cv-tailoring/versions/${encodeURIComponent(
      requireUuid(versionId, 'version_id'),
    )}/source`,
  );
}

export function tailoringPdfUrl(versionId: string): string {
  return apiUrl(
    `/api/cv-tailoring/versions/${encodeURIComponent(
      requireUuid(versionId, 'version_id'),
    )}/pdf`,
  );
}

export type CvTailoringApi = {
  fetchSessions: typeof fetchTailoringSessions;
  fetchSession: typeof fetchTailoringSession;
  streamCreate: typeof streamCreateTailoringSession;
  streamAiVersion: typeof streamCreateTailoringAiVersion;
  createManualVersion: typeof createTailoringManualVersion;
  deleteSession: typeof deleteTailoringSession;
};

export const defaultCvTailoringApi: CvTailoringApi = {
  fetchSessions: fetchTailoringSessions,
  fetchSession: fetchTailoringSession,
  streamCreate: streamCreateTailoringSession,
  streamAiVersion: streamCreateTailoringAiVersion,
  createManualVersion: createTailoringManualVersion,
  deleteSession: deleteTailoringSession,
};

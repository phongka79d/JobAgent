/**
 * Typed observability + CV Manager transport (Plan 8/9).
 * Uses only VITE_API_BASE_URL via shared chat API origin helpers.
 * Never stores or returns raw PDF bytes, storage paths, or secrets.
 * Reprocess SSE is owned by streamCvReprocess in lib/api/chat.ts.
 */

import {
  apiUrl,
  ChatApiError,
  parseErrorBody,
  streamCvReprocess,
} from '../../lib/api/chat';
import {
  asCvDeleteErrorCode,
  asCvReprocessErrorCode,
  CV_DELETE_ERROR_CODES,
  CV_DELETE_RETRY_SUMMARY,
  CV_REPROCESS_ERROR_CODES,
  isRetryableDeleteError,
  toCvManagerActionError,
} from './cvManagerTypes';
import {
  parseChunkDetail,
  parseChunkListPage,
  parseCvHistoryPage,
  parseGraphSnapshot,
  parseRunHistoryPage,
  type ChunkDetail,
  type ChunkListPage,
  type CvHistoryPage,
  type GraphSnapshot,
  type RunHistoryPage,
} from './types';

export {ChatApiError, streamCvReprocess};
export {
  asCvDeleteErrorCode,
  asCvReprocessErrorCode,
  CV_DELETE_ERROR_CODES,
  CV_DELETE_RETRY_SUMMARY,
  CV_REPROCESS_ERROR_CODES,
  isRetryableDeleteError,
  toCvManagerActionError,
};

export type ObservabilityPageQuery = {
  limit?: number;
  before?: string | null;
};

function buildQuery(query: ObservabilityPageQuery = {}): string {
  const params = new URLSearchParams();
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit));
  }
  if (query.before) {
    params.set('before', query.before);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

async function getJson(
  path: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method: 'GET',
    headers: {Accept: 'application/json'},
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    throw parseErrorBody(response.status, text);
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ChatApiError(
      response.status,
      'INVALID_JSON',
      'Observability body is not JSON',
    );
  }
}

/** GET /api/observability/cvs */
export async function fetchCvHistory(
  query: ObservabilityPageQuery = {},
  signal?: AbortSignal,
): Promise<CvHistoryPage> {
  const json = await getJson(`/api/observability/cvs${buildQuery(query)}`, signal);
  try {
    return parseCvHistoryPage(json);
  } catch (err) {
    throw new ChatApiError(
      200,
      'INVALID_CV_HISTORY_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid CV history payload',
    );
  }
}

/** Absolute URL for GET /api/observability/cvs/{id}/file (view/download). */
export function getRetainedCvUrl(attachmentId: string): string {
  return apiUrl(`/api/observability/cvs/${encodeURIComponent(attachmentId)}/file`);
}

/** GET /api/observability/cvs/{id}/chunks */
export async function fetchChunkList(
  attachmentId: string,
  query: ObservabilityPageQuery = {},
  signal?: AbortSignal,
): Promise<ChunkListPage> {
  const path =
    `/api/observability/cvs/${encodeURIComponent(attachmentId)}/chunks` +
    buildQuery(query);
  const json = await getJson(path, signal);
  try {
    return parseChunkListPage(json);
  } catch (err) {
    throw new ChatApiError(
      200,
      'INVALID_CHUNK_LIST_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid chunk list payload',
    );
  }
}

/** GET /api/observability/cvs/{id}/chunks/{ordinal} — full text for one row. */
export async function fetchChunkDetail(
  attachmentId: string,
  ordinal: number,
  signal?: AbortSignal,
): Promise<ChunkDetail> {
  const path =
    `/api/observability/cvs/${encodeURIComponent(attachmentId)}` +
    `/chunks/${encodeURIComponent(String(ordinal))}`;
  const json = await getJson(path, signal);
  try {
    return parseChunkDetail(json);
  } catch (err) {
    throw new ChatApiError(
      200,
      'INVALID_CHUNK_DETAIL_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid chunk detail payload',
    );
  }
}

/** GET /api/observability/runs */
export async function fetchRunHistory(
  query: ObservabilityPageQuery = {},
  signal?: AbortSignal,
): Promise<RunHistoryPage> {
  const json = await getJson(
    `/api/observability/runs${buildQuery(query)}`,
    signal,
  );
  try {
    return parseRunHistoryPage(json);
  } catch (err) {
    throw new ChatApiError(
      200,
      'INVALID_RUN_HISTORY_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid run history payload',
    );
  }
}

/** GET /api/observability/graph */
export async function fetchGraphSnapshot(
  signal?: AbortSignal,
): Promise<GraphSnapshot> {
  const json = await getJson('/api/observability/graph', signal);
  try {
    return parseGraphSnapshot(json);
  } catch (err) {
    throw new ChatApiError(
      200,
      'INVALID_GRAPH_PAYLOAD',
      err instanceof Error ? err.message : 'Invalid graph snapshot payload',
    );
  }
}

/**
 * DELETE /api/cvs/{attachment_id} — complete non-active delete.
 * 204 = success (no body). Maps documented codes; partial cleanup stays retryable.
 * Rejects JSON bodies that smuggle forbidden internal fields on error responses.
 */
export async function deleteCv(
  attachmentId: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/cvs/${encodeURIComponent(attachmentId)}`),
    {
      method: 'DELETE',
      headers: {Accept: 'application/json'},
      signal,
    },
  );
  if (response.status === 204 || response.status === 200) {
    // 204 is the contract; treat empty 200 as success only when body is empty.
    if (response.status === 204) {
      return;
    }
    const text = await response.text();
    if (text.trim() === '') {
      return;
    }
    throw new ChatApiError(
      response.status,
      'INVALID_DELETE_PAYLOAD',
      'Delete success body must be empty',
    );
  }
  const text = await response.text();
  // Reject forbidden keys if a JSON error body includes them.
  try {
    const json = JSON.parse(text) as unknown;
    if (json && typeof json === 'object' && !Array.isArray(json)) {
      const forbidden = [
        'storage_path',
        'file_hash',
        'checkpoint',
        'api_key',
        'SHOPAIKEY_API_KEY',
      ];
      for (const key of forbidden) {
        if (key in (json as Record<string, unknown>)) {
          throw new ChatApiError(
            response.status,
            'FORBIDDEN_FIELD',
            `Delete error must not include ${key}`,
          );
        }
        const detail = (json as {detail?: unknown}).detail;
        if (
          detail &&
          typeof detail === 'object' &&
          !Array.isArray(detail) &&
          key in (detail as Record<string, unknown>)
        ) {
          throw new ChatApiError(
            response.status,
            'FORBIDDEN_FIELD',
            `Delete error must not include ${key}`,
          );
        }
      }
    }
  } catch (err) {
    if (err instanceof ChatApiError && err.code === 'FORBIDDEN_FIELD') {
      throw err;
    }
    // non-JSON handled by parseErrorBody
  }
  const mapped = parseErrorBody(response.status, text);
  const known = asCvDeleteErrorCode(mapped.code);
  if (known && isRetryableDeleteError(known)) {
    throw new ChatApiError(
      response.status,
      known,
      CV_DELETE_RETRY_SUMMARY,
    );
  }
  if (known) {
    throw new ChatApiError(response.status, known, mapped.summary);
  }
  throw mapped;
}

export type ObservabilityApi = {
  fetchCvHistory: typeof fetchCvHistory;
  fetchChunkList: typeof fetchChunkList;
  fetchChunkDetail: typeof fetchChunkDetail;
  fetchRunHistory: typeof fetchRunHistory;
  fetchGraphSnapshot: typeof fetchGraphSnapshot;
  getRetainedCvUrl: typeof getRetainedCvUrl;
  deleteCv: typeof deleteCv;
  streamCvReprocess: typeof streamCvReprocess;
};

export const defaultObservabilityApi: ObservabilityApi = {
  fetchCvHistory,
  fetchChunkList,
  fetchChunkDetail,
  fetchRunHistory,
  fetchGraphSnapshot,
  getRetainedCvUrl,
  deleteCv,
  streamCvReprocess,
};

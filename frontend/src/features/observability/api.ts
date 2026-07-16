/**
 * Typed observability transport (Plan 8).
 * Uses only VITE_API_BASE_URL via shared chat API origin helpers.
 * Never stores or returns raw PDF bytes, storage paths, or secrets.
 */

import {
  apiUrl,
  ChatApiError,
  parseErrorBody,
} from '../../lib/api/chat';
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

export {ChatApiError};

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

export type ObservabilityApi = {
  fetchCvHistory: typeof fetchCvHistory;
  fetchChunkList: typeof fetchChunkList;
  fetchChunkDetail: typeof fetchChunkDetail;
  fetchRunHistory: typeof fetchRunHistory;
  fetchGraphSnapshot: typeof fetchGraphSnapshot;
  getRetainedCvUrl: typeof getRetainedCvUrl;
};

export const defaultObservabilityApi: ObservabilityApi = {
  fetchCvHistory,
  fetchChunkList,
  fetchChunkDetail,
  fetchRunHistory,
  fetchGraphSnapshot,
  getRetainedCvUrl,
};

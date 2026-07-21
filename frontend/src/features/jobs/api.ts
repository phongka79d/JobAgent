/**
 * Typed saved-JD transport (Plan 10 / Master §7.7 / §14.1).
 * Uses only VITE_API_BASE_URL via shared chat API origin helpers.
 * Never stores or returns embeddings, prompts, storage paths, or secrets.
 */

import {
  apiUrl,
  ChatApiError,
  parseErrorBody,
} from '../../lib/api/chat';
import {
  parseEvaluateJobResponse,
  parseReextractJobResponse,
  parseSaveAndEvaluateResponse,
  parseSavedJobDetail,
  parseSavedJobListPage,
  type EvaluateJobResponse,
  type ReextractJobResponse,
  type SaveAndEvaluateResponse,
  type SavedJobDetail,
  type SavedJobListPage,
  type SavedJobsPageQuery,
} from './types';

export {ChatApiError};

/** Documented saved-JD mutation/read error codes (Batch04 public API). */
export const SAVED_JOB_ERROR_CODES = {
  JOB_NOT_FOUND: 'JOB_NOT_FOUND',
  JD_SOURCE_NOT_RECOVERABLE: 'JD_SOURCE_NOT_RECOVERABLE',
  JOB_NOT_SCORABLE: 'JOB_NOT_SCORABLE',
  ACTIVE_PROFILE_REQUIRED: 'ACTIVE_PROFILE_REQUIRED',
  JOB_DELETE_GRAPH_FAILED: 'JOB_DELETE_GRAPH_FAILED',
  JOB_REEXTRACT_CONFLICT: 'JOB_REEXTRACT_CONFLICT',
  EVALUATION_CONTEXT_CHANGED: 'EVALUATION_CONTEXT_CHANGED',
  INVALID_MATCH_RESULT: 'INVALID_MATCH_RESULT',
  INVALID_LIMIT: 'INVALID_LIMIT',
  NEO4J_UNAVAILABLE: 'NEO4J_UNAVAILABLE',
  NEO4J_REBUILD_REQUIRED: 'NEO4J_REBUILD_REQUIRED',
  NEO4J_SYNC_FAILED: 'NEO4J_SYNC_FAILED',
  EMBEDDING_TIMEOUT: 'EMBEDDING_TIMEOUT',
  EMBEDDING_UNAVAILABLE: 'EMBEDDING_UNAVAILABLE',
  EMBEDDING_INVALID_RESPONSE: 'EMBEDDING_INVALID_RESPONSE',
} as const;

export type SavedJobErrorCode =
  (typeof SAVED_JOB_ERROR_CODES)[keyof typeof SAVED_JOB_ERROR_CODES];

const SAVED_JOB_ERROR_CODE_SET: ReadonlySet<string> = new Set(
  Object.values(SAVED_JOB_ERROR_CODES),
);

/** Partial delete / graph failure may retain SQLite until retry. */
export const SAVED_JOB_DELETE_RETRY_SUMMARY =
  'Job deletion is incomplete because graph cleanup failed. ' +
  'Retry DELETE for the same job id.';

const RETRYABLE_DELETE_CODES: ReadonlySet<string> = new Set([
  SAVED_JOB_ERROR_CODES.JOB_DELETE_GRAPH_FAILED,
]);

const FORBIDDEN_ERROR_KEYS = [
  'storage_path',
  'file_hash',
  'checkpoint',
  'api_key',
  'SHOPAIKEY_API_KEY',
  'embedding',
  'embeddings',
  'raw_content',
  'result_json',
  'cypher',
  'sql',
] as const;

export function asSavedJobErrorCode(code: string): SavedJobErrorCode | null {
  return SAVED_JOB_ERROR_CODE_SET.has(code)
    ? (code as SavedJobErrorCode)
    : null;
}

export function isRetryableSavedJobDeleteError(code: string): boolean {
  return RETRYABLE_DELETE_CODES.has(code);
}

export function toSavedJobActionError(
  err: unknown,
  fallbackCode = 'REQUEST_FAILED',
): {code: string; summary: string; retryable: boolean} {
  let code = fallbackCode;
  let summary = 'Request failed';
  if (err instanceof ChatApiError) {
    code = err.code;
    summary = err.summary;
  } else if (
    err &&
    typeof err === 'object' &&
    'code' in err &&
    'summary' in err &&
    typeof (err as {code: unknown}).code === 'string' &&
    typeof (err as {summary: unknown}).summary === 'string'
  ) {
    code = (err as {code: string}).code;
    summary = (err as {summary: string}).summary;
  } else if (err instanceof Error) {
    summary = err.message;
  }
  const retryable = isRetryableSavedJobDeleteError(code);
  if (retryable) {
    return {code, summary: SAVED_JOB_DELETE_RETRY_SUMMARY, retryable: true};
  }
  return {code, summary, retryable: false};
}

function buildQuery(query: SavedJobsPageQuery = {}): string {
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

function rejectForbiddenErrorFields(
  status: number,
  text: string,
): void {
  try {
    const json = JSON.parse(text) as unknown;
    if (!json || typeof json !== 'object' || Array.isArray(json)) {
      return;
    }
    const root = json as Record<string, unknown>;
    for (const key of FORBIDDEN_ERROR_KEYS) {
      if (key in root) {
        throw new ChatApiError(
          status,
          'FORBIDDEN_FIELD',
          `Error must not include ${key}`,
        );
      }
      const detail = root.detail;
      if (
        detail &&
        typeof detail === 'object' &&
        !Array.isArray(detail) &&
        key in (detail as Record<string, unknown>)
      ) {
        throw new ChatApiError(
          status,
          'FORBIDDEN_FIELD',
          `Error must not include ${key}`,
        );
      }
    }
  } catch (err) {
    if (err instanceof ChatApiError && err.code === 'FORBIDDEN_FIELD') {
      throw err;
    }
  }
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
    rejectForbiddenErrorFields(response.status, text);
    throw parseErrorBody(response.status, text);
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ChatApiError(
      response.status,
      'INVALID_JSON',
      'Saved-JD body is not JSON',
    );
  }
}

async function postJson(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    rejectForbiddenErrorFields(response.status, text);
    const mapped = parseErrorBody(response.status, text);
    const known = asSavedJobErrorCode(mapped.code);
    if (known && isRetryableSavedJobDeleteError(known)) {
      throw new ChatApiError(
        response.status,
        known,
        SAVED_JOB_DELETE_RETRY_SUMMARY,
      );
    }
    if (known) {
      throw new ChatApiError(response.status, known, mapped.summary);
    }
    throw mapped;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ChatApiError(
      response.status,
      'INVALID_JSON',
      'Saved-JD body is not JSON',
    );
  }
}

function wrapParseError(code: string, err: unknown): ChatApiError {
  return new ChatApiError(
    200,
    code,
    err instanceof Error ? err.message : 'Invalid saved-JD payload',
  );
}

/** GET /api/jobs — compact cursor page. */
export async function fetchSavedJobs(
  query: SavedJobsPageQuery = {},
  signal?: AbortSignal,
): Promise<SavedJobListPage> {
  const json = await getJson(`/api/jobs${buildQuery(query)}`, signal);
  try {
    return parseSavedJobListPage(json);
  } catch (err) {
    throw wrapParseError('INVALID_SAVED_JOBS_LIST_PAYLOAD', err);
  }
}

/** GET /api/jobs/{job_id} — selected detail. */
export async function fetchSavedJobDetail(
  jobId: string,
  signal?: AbortSignal,
): Promise<SavedJobDetail> {
  const path = `/api/jobs/${encodeURIComponent(jobId)}`;
  const json = await getJson(path, signal);
  try {
    return parseSavedJobDetail(json);
  } catch (err) {
    throw wrapParseError('INVALID_SAVED_JOB_DETAIL_PAYLOAD', err);
  }
}

/** POST /api/jobs/{job_id}/evaluate — create or reuse current evaluation. */
export async function evaluateSavedJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<EvaluateJobResponse> {
  const path = `/api/jobs/${encodeURIComponent(jobId)}/evaluate`;
  const json = await postJson(path, {}, signal);
  try {
    return parseEvaluateJobResponse(json);
  } catch (err) {
    throw wrapParseError('INVALID_EVALUATE_PAYLOAD', err);
  }
}

/**
 * POST /api/jobs/save-and-evaluate — durable initiating message only.
 * Never accepts client-supplied JD body replacement.
 */
export async function saveAndEvaluateJob(
  sourceMessageId: string,
  signal?: AbortSignal,
): Promise<SaveAndEvaluateResponse> {
  const json = await postJson(
    '/api/jobs/save-and-evaluate',
    {source_message_id: sourceMessageId},
    signal,
  );
  try {
    return parseSaveAndEvaluateResponse(json);
  } catch (err) {
    throw wrapParseError('INVALID_SAVE_AND_EVALUATE_PAYLOAD', err);
  }
}

/**
 * POST /api/jobs/{job_id}/reextract — same-ID retained-JD replacement.
 * Empty body only; never accepts client replacement fields.
 * HTTP 200 may still report graph partial success (sync_ok=false).
 */
export async function reextractSavedJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<ReextractJobResponse> {
  const path = `/api/jobs/${encodeURIComponent(jobId)}/reextract`;
  const json = await postJson(path, {}, signal);
  try {
    return parseReextractJobResponse(json);
  } catch (err) {
    throw wrapParseError('INVALID_REEXTRACT_PAYLOAD', err);
  }
}

/**
 * DELETE /api/jobs/{job_id} — complete deletion.
 * 204 = success (no body). Maps documented codes; graph failure stays retryable.
 */
export async function deleteSavedJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/jobs/${encodeURIComponent(jobId)}`),
    {
      method: 'DELETE',
      headers: {Accept: 'application/json'},
      signal,
    },
  );
  if (response.status === 204 || response.status === 200) {
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
  rejectForbiddenErrorFields(response.status, text);
  const mapped = parseErrorBody(response.status, text);
  const known = asSavedJobErrorCode(mapped.code);
  if (known && isRetryableSavedJobDeleteError(known)) {
    throw new ChatApiError(
      response.status,
      known,
      SAVED_JOB_DELETE_RETRY_SUMMARY,
    );
  }
  if (known) {
    throw new ChatApiError(response.status, known, mapped.summary);
  }
  throw mapped;
}

export type SavedJobsApi = {
  fetchSavedJobs: typeof fetchSavedJobs;
  fetchSavedJobDetail: typeof fetchSavedJobDetail;
  evaluateSavedJob: typeof evaluateSavedJob;
  saveAndEvaluateJob: typeof saveAndEvaluateJob;
  reextractSavedJob: typeof reextractSavedJob;
  deleteSavedJob: typeof deleteSavedJob;
};

export const defaultSavedJobsApi: SavedJobsApi = {
  fetchSavedJobs,
  fetchSavedJobDetail,
  evaluateSavedJob,
  saveAndEvaluateJob,
  reextractSavedJob,
  deleteSavedJob,
};

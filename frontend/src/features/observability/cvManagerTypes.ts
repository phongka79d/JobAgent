/**
 * CV Manager action contracts (Plan 9 / Master §14.1).
 * Stable reprocess/delete codes and pending-action shapes only.
 * Transport parsers and SSE ownership stay in api.ts / chat.ts.
 */

import type {ObservabilitySafeError} from './types';

/** Per-attachment action kinds tracked in sidebar-local state. */
export type CvManagerActionKind = 'reprocess' | 'delete';

/** Documented reprocess precondition / HTTP error codes (Master §14.1). */
export const CV_REPROCESS_ERROR_CODES = {
  APPROVAL_ACTION_REQUIRED: 'APPROVAL_ACTION_REQUIRED',
  CV_ATTACHMENT_NOT_FOUND: 'CV_ATTACHMENT_NOT_FOUND',
  CV_NOT_REPROCESSABLE: 'CV_NOT_REPROCESSABLE',
  CV_FILE_UNAVAILABLE: 'CV_FILE_UNAVAILABLE',
  CHUNKS_UNAVAILABLE: 'CHUNKS_UNAVAILABLE',
} as const;

export type CvReprocessErrorCode =
  (typeof CV_REPROCESS_ERROR_CODES)[keyof typeof CV_REPROCESS_ERROR_CODES];

/** Documented delete error codes (Master §10.5 / §14.1 / §20). */
export const CV_DELETE_ERROR_CODES = {
  CV_ATTACHMENT_NOT_FOUND: 'CV_ATTACHMENT_NOT_FOUND',
  CV_ACTIVE_DELETE_FORBIDDEN: 'CV_ACTIVE_DELETE_FORBIDDEN',
  CV_DELETE_CHECKPOINT_FAILED: 'CV_DELETE_CHECKPOINT_FAILED',
  CV_DELETE_FILE_FAILED: 'CV_DELETE_FILE_FAILED',
  CV_DELETE_GRAPH_FAILED: 'CV_DELETE_GRAPH_FAILED',
  CV_DELETE_FINALIZE_FAILED: 'CV_DELETE_FINALIZE_FAILED',
} as const;

export type CvDeleteErrorCode =
  (typeof CV_DELETE_ERROR_CODES)[keyof typeof CV_DELETE_ERROR_CODES];

/** Safe retry guidance for partial cleanup (mirrors backend CV_DELETE_RETRY_SUMMARY). */
export const CV_DELETE_RETRY_SUMMARY =
  'CV deletion is incomplete; the attachment remains in deleting state. ' +
  'Retry DELETE for the same attachment id.';

const REPROCESS_CODE_SET: ReadonlySet<string> = new Set(
  Object.values(CV_REPROCESS_ERROR_CODES),
);

const DELETE_CODE_SET: ReadonlySet<string> = new Set(
  Object.values(CV_DELETE_ERROR_CODES),
);

/** Partial-cleanup codes where the row remains and DELETE may be retried. */
const RETRYABLE_DELETE_CODES: ReadonlySet<string> = new Set([
  CV_DELETE_ERROR_CODES.CV_DELETE_CHECKPOINT_FAILED,
  CV_DELETE_ERROR_CODES.CV_DELETE_FILE_FAILED,
  CV_DELETE_ERROR_CODES.CV_DELETE_GRAPH_FAILED,
  CV_DELETE_ERROR_CODES.CV_DELETE_FINALIZE_FAILED,
]);

/** Classify a raw code as a known reprocess error (else null). */
export function asCvReprocessErrorCode(
  code: string,
): CvReprocessErrorCode | null {
  return REPROCESS_CODE_SET.has(code) ? (code as CvReprocessErrorCode) : null;
}

/** Classify a raw code as a known delete error (else null). */
export function asCvDeleteErrorCode(code: string): CvDeleteErrorCode | null {
  return DELETE_CODE_SET.has(code) ? (code as CvDeleteErrorCode) : null;
}

/** True when DELETE failed after partial cleanup and retry is safe. */
export function isRetryableDeleteError(code: string): boolean {
  return RETRYABLE_DELETE_CODES.has(code);
}

/**
 * Map a transport error to a safe sidebar message.
 * Known delete partial codes force the documented retry summary.
 */
export function toCvManagerActionError(
  err: unknown,
  fallbackCode = 'REQUEST_FAILED',
): ObservabilitySafeError & {retryable: boolean} {
  let code = fallbackCode;
  let summary = 'Request failed';
  if (
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
  const retryable = isRetryableDeleteError(code);
  if (retryable) {
    return {code, summary: CV_DELETE_RETRY_SUMMARY, retryable: true};
  }
  return {code, summary, retryable: false};
}

/** Prefer active, else first remaining non-deleted row. */
export function selectSafeRemainingAttachmentId(
  items: ReadonlyArray<{id: string; state: string}>,
  deletedId: string,
  currentSelection: string | null,
): string | null {
  const remaining = items.filter((item) => item.id !== deletedId);
  if (remaining.length === 0) {
    return null;
  }
  if (
    currentSelection &&
    currentSelection !== deletedId &&
    remaining.some((item) => item.id === currentSelection)
  ) {
    return currentSelection;
  }
  const active = remaining.find((item) => item.state === 'active');
  if (active) {
    return active.id;
  }
  return remaining[0]?.id ?? null;
}

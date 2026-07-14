/**
 * Strict compact save_job ToolResult projection (Plan 5 §7.6 / §7.9).
 * Parses durable ToolResult.data only — never assistant prose or SSE payloads.
 */

import type {JsonObject, JsonValue} from '../chat/types';

/** Exact job_posts.processing_status vocabulary. */
export type JobProcessingStatus =
  | 'received'
  | 'processing'
  | 'processed'
  | 'failed';

/** Exact job_posts.jd_quality vocabulary when processed. */
export type JobJdQuality = 'full' | 'partial' | 'unscorable';

/** Ingestion outcome vocabulary from save_job ToolResult.data. */
export type JobIngestOutcome = 'created' | 'returned' | 'retried';

export const JOB_PROCESSING_STATUSES: readonly JobProcessingStatus[] = [
  'received',
  'processing',
  'processed',
  'failed',
] as const;

export const JOB_JD_QUALITIES: readonly JobJdQuality[] = [
  'full',
  'partial',
  'unscorable',
] as const;

export const JOB_INGEST_OUTCOMES: readonly JobIngestOutcome[] = [
  'created',
  'returned',
  'retried',
] as const;

export const SAVE_JOB_TOOL_NAME = 'save_job' as const;
export const QUERY_JOBS_TOOL_NAME = 'query_jobs' as const;

export const NEO4J_SYNC_FAILED_CODE = 'NEO4J_SYNC_FAILED' as const;

/**
 * Exact SaveJobResultData keys (backend compact contract).
 * Durable history retains only this allowlist for save_job.
 */
export const SAVE_JOB_RESULT_DATA_KEYS = [
  'job_id',
  'title',
  'company',
  'source_url',
  'processing_status',
  'jd_quality',
  'outcome',
  'sqlite_committed',
  'sync_ok',
  'failure_code',
  'rebuild_instruction',
  'paste_instruction',
] as const;

const SAVE_JOB_RESULT_KEY_SET: ReadonlySet<string> = new Set(
  SAVE_JOB_RESULT_DATA_KEYS,
);

/** Compact save_job card projection — never raw JD or embeddings. */
export interface CompactSaveJobResult {
  jobId: string;
  title: string | null;
  company: string | null;
  sourceUrl: string | null;
  processingStatus: JobProcessingStatus;
  jdQuality: JobJdQuality | null;
  outcome: JobIngestOutcome;
  sqliteCommitted: boolean;
  syncOk: boolean | null;
  failureCode: string | null;
  rebuildInstruction: string | null;
  pasteInstruction: string | null;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asNullableString(value: unknown): string | null | undefined {
  if (value === null) {
    return null;
  }
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== 'string') {
    return undefined;
  }
  return value;
}

function asBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function asNullableBoolean(value: unknown): boolean | null | undefined {
  if (value === null) {
    return null;
  }
  if (value === undefined) {
    return undefined;
  }
  return typeof value === 'boolean' ? value : undefined;
}

/**
 * Accept only http(s) absolute URLs for display; reject javascript: and relatives.
 */
export function safeHttpUrl(value: string | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  const trimmed = value.trim();
  if (trimmed === '') {
    return null;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

/**
 * Copy only SaveJobResultData allowlist keys from a plain object.
 * Never retains secrets, storage paths, nested raw bodies, or other tools' data.
 */
function allowlistSaveJobResultData(
  data: Record<string, unknown>,
): JsonObject {
  const out: JsonObject = {};
  for (const key of SAVE_JOB_RESULT_DATA_KEYS) {
    if (Object.prototype.hasOwnProperty.call(data, key)) {
      out[key] = data[key] as JsonValue;
    }
  }
  return out;
}

/**
 * Strict parse of compact save_job ToolResult.data.
 * Requires every contract field (nullable fields must be present as null),
 * rejects unexpected keys, and returns null on any vocabulary/type failure.
 * Single parser owner — no second save_job parser.
 */
export function parseSaveJobResultData(
  data: JsonObject | null | undefined,
): CompactSaveJobResult | null {
  if (!isObject(data)) {
    return null;
  }

  for (const key of Object.keys(data)) {
    if (!SAVE_JOB_RESULT_KEY_SET.has(key)) {
      return null;
    }
  }

  const jobIdRaw = data.job_id;
  if (typeof jobIdRaw !== 'string' || jobIdRaw.trim() === '') {
    return null;
  }

  const processingRaw = data.processing_status;
  if (
    typeof processingRaw !== 'string' ||
    !(JOB_PROCESSING_STATUSES as readonly string[]).includes(processingRaw)
  ) {
    return null;
  }

  if (!Object.prototype.hasOwnProperty.call(data, 'jd_quality')) {
    return null;
  }
  const qualityRaw = data.jd_quality;
  let jdQuality: JobJdQuality | null;
  if (qualityRaw === null) {
    jdQuality = null;
  } else if (
    typeof qualityRaw === 'string' &&
    (JOB_JD_QUALITIES as readonly string[]).includes(qualityRaw)
  ) {
    jdQuality = qualityRaw as JobJdQuality;
  } else {
    return null;
  }

  const outcomeRaw = data.outcome;
  if (
    typeof outcomeRaw !== 'string' ||
    !(JOB_INGEST_OUTCOMES as readonly string[]).includes(outcomeRaw)
  ) {
    return null;
  }

  const sqliteCommitted = asBoolean(data.sqlite_committed);
  if (sqliteCommitted === undefined) {
    return null;
  }

  if (!Object.prototype.hasOwnProperty.call(data, 'title')) {
    return null;
  }
  const title = asNullableString(data.title);
  if (title === undefined) {
    return null;
  }
  if (!Object.prototype.hasOwnProperty.call(data, 'company')) {
    return null;
  }
  const company = asNullableString(data.company);
  if (company === undefined) {
    return null;
  }
  if (!Object.prototype.hasOwnProperty.call(data, 'source_url')) {
    return null;
  }
  const sourceUrlRaw = asNullableString(data.source_url);
  if (sourceUrlRaw === undefined) {
    return null;
  }

  // sync_ok is required and nullable — missing key is not equivalent to null.
  if (!Object.prototype.hasOwnProperty.call(data, 'sync_ok')) {
    return null;
  }
  const syncOk = asNullableBoolean(data.sync_ok);
  if (syncOk === undefined) {
    return null;
  }

  if (!Object.prototype.hasOwnProperty.call(data, 'failure_code')) {
    return null;
  }
  const failureCode = asNullableString(data.failure_code);
  if (failureCode === undefined) {
    return null;
  }
  if (!Object.prototype.hasOwnProperty.call(data, 'rebuild_instruction')) {
    return null;
  }
  const rebuildInstruction = asNullableString(data.rebuild_instruction);
  if (rebuildInstruction === undefined) {
    return null;
  }
  if (!Object.prototype.hasOwnProperty.call(data, 'paste_instruction')) {
    return null;
  }
  const pasteInstruction = asNullableString(data.paste_instruction);
  if (pasteInstruction === undefined) {
    return null;
  }

  return {
    jobId: jobIdRaw,
    title: title === null || title.trim() === '' ? null : title,
    company: company === null || company.trim() === '' ? null : company,
    sourceUrl: safeHttpUrl(sourceUrlRaw),
    processingStatus: processingRaw as JobProcessingStatus,
    jdQuality,
    outcome: outcomeRaw as JobIngestOutcome,
    sqliteCommitted,
    syncOk,
    failureCode:
      failureCode === null || failureCode.trim() === '' ? null : failureCode,
    rebuildInstruction:
      rebuildInstruction === null || rebuildInstruction.trim() === ''
        ? null
        : rebuildInstruction,
    pasteInstruction:
      pasteInstruction === null || pasteInstruction.trim() === ''
        ? null
        : pasteInstruction,
  };
}

/**
 * Durable history boundary projection for ToolResult.data.
 * Exact save_job / SaveJobResultData allowlist only; unrelated tools retain
 * no resultData unless an explicit source-owned projection is added here.
 */
export function projectCompactResultData(
  toolName: string,
  data: JsonObject | null | undefined,
): JsonObject | null {
  if (toolName !== SAVE_JOB_TOOL_NAME) {
    return null;
  }
  if (!isObject(data)) {
    return null;
  }
  // Strip non-contract keys first, then require the single exact parser.
  const slim = allowlistSaveJobResultData(data);
  if (parseSaveJobResultData(slim) === null) {
    return null;
  }
  return slim;
}

/** True when tool result data is a compact save_job projection. */
export function isSaveJobToolName(toolName: string): boolean {
  return toolName === SAVE_JOB_TOOL_NAME;
}

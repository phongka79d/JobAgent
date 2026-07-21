/**
 * Strict compact save_job ToolResult projection (Plan 5 §7.6 / §7.9).
 * Parses durable ToolResult.data only — never assistant prose or SSE payloads.
 * Also owns Plan 10 saved-JD public view parsers (Master §7.7) — mirror Batch04
 * schemas strictly; reuse parseMatchResult for evaluation.result.
 */

import type {JsonObject, JsonValue} from '../chat/types';
import {
  parseMatchResult,
  type CompactMatchResult,
  type JobWorkMode,
  JOB_WORK_MODES,
} from './matchResult';

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

// ---------------------------------------------------------------------------
// Plan 10 / Master §7.7 — public saved-JD list/detail/action view contracts
// ---------------------------------------------------------------------------

export type EvaluationCurrentness = 'none' | 'current' | 'stale';
export type EvaluationRowState = 'current' | 'stale';
export type JobSourceType = 'url' | 'text';
export type JobSeniority =
  | 'intern'
  | 'junior'
  | 'mid'
  | 'senior'
  | 'lead'
  | 'unknown';

/** Public save-and-evaluate ingest outcome (internal returned → existing). */
export type SaveIngestOutcome = 'created' | 'existing' | 'retried';
export type SaveEvaluationOutcome = 'created' | 'reused' | 'unavailable';
export type EvaluateOutcome = 'created' | 'reused';

/** Re-extraction success outcome (Plan 15 public contract). */
export type ReextractOutcome = 'updated';

export type SavedJobsSafeError = {
  code: string;
  summary: string;
};

export const EVALUATION_CURRENTNESS: readonly EvaluationCurrentness[] = [
  'none',
  'current',
  'stale',
] as const;

export const EVALUATION_ROW_STATES: readonly EvaluationRowState[] = [
  'current',
  'stale',
] as const;

export const JOB_SOURCE_TYPES: readonly JobSourceType[] = [
  'url',
  'text',
] as const;

export const JOB_SENIORITIES: readonly JobSeniority[] = [
  'intern',
  'junior',
  'mid',
  'senior',
  'lead',
  'unknown',
] as const;

export const SAVE_INGEST_OUTCOMES: readonly SaveIngestOutcome[] = [
  'created',
  'existing',
  'retried',
] as const;

export const SAVE_EVALUATION_OUTCOMES: readonly SaveEvaluationOutcome[] = [
  'created',
  'reused',
  'unavailable',
] as const;

export const EVALUATE_OUTCOMES: readonly EvaluateOutcome[] = [
  'created',
  'reused',
] as const;

export const REEXTRACT_OUTCOMES: readonly ReextractOutcome[] = [
  'updated',
] as const;

/** Coupled graph-failure code on re-extract success when sync_ok=false. */
export const REEXTRACT_GRAPH_FAILURE_CODE = 'NEO4J_SYNC_FAILED' as const;

export const SAVED_JOBS_LIMIT_MIN = 1;
export const SAVED_JOBS_LIMIT_MAX = 50;
export const SAVED_JOBS_DEFAULT_LIMIT = 50;

/** Keys never allowed on compact list rows (Master §7.7 redaction). */
export const SAVED_JOB_LIST_FORBIDDEN_KEYS: readonly string[] = [
  'raw_content',
  'raw_content_hash',
  'extraction',
  'extraction_json',
  'embedding',
  'embeddings',
  'embedding_json',
  'embedding_model',
  'embedding_dimensions',
  'prompt',
  'prompts',
  'storage_path',
  'api_key',
  'SHOPAIKEY_API_KEY',
  'result_json',
  'historical',
  'evaluations',
  'graph',
  'provider',
  'cypher',
  'sql',
  'checkpoint',
] as const;

const LIST_FORBIDDEN_SET: ReadonlySet<string> = new Set(
  SAVED_JOB_LIST_FORBIDDEN_KEYS,
);

const SAVED_JOB_LIST_ITEM_KEYS = [
  'id',
  'title',
  'company',
  'processing_status',
  'jd_quality',
  'source_type',
  'source_url',
  'created_at',
  'updated_at',
  'evaluation_state',
  'latest_score',
] as const;

const SAVED_JOB_LIST_ITEM_KEY_SET: ReadonlySet<string> = new Set(
  SAVED_JOB_LIST_ITEM_KEYS,
);

const JOB_EVALUATION_VIEW_KEYS = [
  'id',
  'job_id',
  'evaluation_state',
  'evaluation_context_hash',
  'result',
  'created_at',
  'updated_at',
] as const;

const JOB_EVALUATION_VIEW_KEY_SET: ReadonlySet<string> = new Set(
  JOB_EVALUATION_VIEW_KEYS,
);

const SAVED_JOB_DETAIL_KEYS = [
  'compact',
  'extraction',
  'raw_content',
  'latest_evaluation',
] as const;

const SAVED_JOB_DETAIL_KEY_SET: ReadonlySet<string> = new Set(
  SAVED_JOB_DETAIL_KEYS,
);

const SAVED_JOB_LIST_PAGE_KEYS = ['items', 'next_cursor'] as const;
const SAVED_JOB_LIST_PAGE_KEY_SET: ReadonlySet<string> = new Set(
  SAVED_JOB_LIST_PAGE_KEYS,
);

const EVALUATE_RESPONSE_KEYS = ['outcome', 'job', 'evaluation'] as const;
const EVALUATE_RESPONSE_KEY_SET: ReadonlySet<string> = new Set(
  EVALUATE_RESPONSE_KEYS,
);

const SAVE_AND_EVALUATE_RESPONSE_KEYS = [
  'ingest_outcome',
  'job',
  'evaluation_outcome',
  'evaluation',
  'code',
] as const;
const SAVE_AND_EVALUATE_RESPONSE_KEY_SET: ReadonlySet<string> = new Set(
  SAVE_AND_EVALUATE_RESPONSE_KEYS,
);

const REEXTRACT_RESPONSE_KEYS = [
  'outcome',
  'job',
  'sync_ok',
  'code',
  'rebuild_instruction',
] as const;
const REEXTRACT_RESPONSE_KEY_SET: ReadonlySet<string> = new Set(
  REEXTRACT_RESPONSE_KEYS,
);

const EXTRACTION_KEYS = [
  'title',
  'company',
  'summary',
  'responsibilities',
  'required_skills',
  'preferred_skills',
  'seniority',
  'min_experience_years',
  'max_experience_years',
  'location',
  'work_mode',
  'extraction_confidence',
] as const;
const EXTRACTION_KEY_SET: ReadonlySet<string> = new Set(EXTRACTION_KEYS);

const JOB_SKILL_KEYS = ['skill', 'confidence', 'evidence'] as const;
const JOB_SKILL_KEY_SET: ReadonlySet<string> = new Set(JOB_SKILL_KEYS);

const SKILL_REF_KEYS = [
  'canonical_key',
  'display_name',
  'aliases',
  'category',
] as const;
const SKILL_REF_KEY_SET: ReadonlySet<string> = new Set(SKILL_REF_KEYS);

export type SkillRefView = {
  canonical_key: string;
  display_name: string;
  aliases: string[];
  category: string | null;
};

export type JobSkillView = {
  skill: SkillRefView;
  confidence: number;
  evidence: string[];
};

export type JobPostExtractionView = {
  title: string | null;
  company: string | null;
  summary: string;
  responsibilities: string[];
  required_skills: JobSkillView[];
  preferred_skills: JobSkillView[];
  seniority: JobSeniority;
  min_experience_years: number | null;
  max_experience_years: number | null;
  location: string | null;
  work_mode: JobWorkMode;
  extraction_confidence: number;
};

export type SavedJobListItem = {
  id: string;
  title: string | null;
  company: string | null;
  processing_status: JobProcessingStatus;
  jd_quality: JobJdQuality | null;
  source_type: JobSourceType;
  source_url: string | null;
  created_at: string;
  updated_at: string;
  evaluation_state: EvaluationCurrentness;
  latest_score: number | null;
};

export type SavedJobListPage = {
  items: SavedJobListItem[];
  next_cursor: string | null;
};

export type JobEvaluationView = {
  id: string;
  job_id: string;
  evaluation_state: EvaluationRowState;
  evaluation_context_hash: string;
  result: CompactMatchResult;
  created_at: string;
  updated_at: string;
};

export type SavedJobDetail = {
  compact: SavedJobListItem;
  extraction: JobPostExtractionView | null;
  raw_content: string | null;
  latest_evaluation: JobEvaluationView | null;
};

export type EvaluateJobResponse = {
  outcome: EvaluateOutcome;
  job: SavedJobListItem;
  evaluation: JobEvaluationView;
};

export type SaveAndEvaluateResponse = {
  ingest_outcome: SaveIngestOutcome;
  job: SavedJobListItem;
  evaluation_outcome: SaveEvaluationOutcome;
  evaluation: JobEvaluationView | null;
  code: string | null;
};

/**
 * POST /api/jobs/{job_id}/reextract success after SQLite commit.
 * sync_ok couples code/rebuild_instruction; never coerce malformed combos.
 */
export type ReextractJobResponse = {
  outcome: ReextractOutcome;
  job: SavedJobListItem;
  sync_ok: boolean;
  code: string | null;
  rebuild_instruction: string | null;
};

export type SavedJobsPageQuery = {
  limit?: number;
  before?: string | null;
};

function hasOnlyKeys(
  data: Record<string, unknown>,
  allowed: ReadonlySet<string>,
): boolean {
  for (const key of Object.keys(data)) {
    if (!allowed.has(key)) {
      return false;
    }
  }
  return true;
}

function rejectForbiddenKeys(
  raw: Record<string, unknown>,
  label: string,
): void {
  for (const key of Object.keys(raw)) {
    if (LIST_FORBIDDEN_SET.has(key)) {
      throw new Error(`${label} must not include ${key}`);
    }
  }
}

function requireKeys(
  data: Record<string, unknown>,
  keys: readonly string[],
  label: string,
): void {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(data, key)) {
      throw new Error(`${label} missing required key ${key}`);
    }
  }
}

function asNonEmptyString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function asNullableDisplayString(
  value: unknown,
  label: string,
): string | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== 'string') {
    throw new Error(`${label} must be string or null`);
  }
  return value.trim() === '' ? null : value;
}

function asFiniteNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  return value;
}

function asNullableFiniteNumber(
  value: unknown,
  label: string,
): number | null {
  if (value === null) {
    return null;
  }
  return asFiniteNumber(value, label);
}

function asStringList(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be an array`);
  }
  const out: string[] = [];
  for (let i = 0; i < value.length; i++) {
    if (typeof value[i] !== 'string') {
      throw new Error(`${label}[${i}] must be a string`);
    }
    out.push(value[i] as string);
  }
  return out;
}

function parseSkillRef(raw: unknown, label: string): SkillRefView {
  if (!isObject(raw) || !hasOnlyKeys(raw, SKILL_REF_KEY_SET)) {
    throw new Error(`${label} has invalid skill ref shape`);
  }
  requireKeys(raw, SKILL_REF_KEYS, label);
  return {
    canonical_key: asNonEmptyString(raw.canonical_key, `${label}.canonical_key`),
    display_name: asNonEmptyString(raw.display_name, `${label}.display_name`),
    aliases: asStringList(raw.aliases, `${label}.aliases`),
    category: asNullableDisplayString(raw.category, `${label}.category`),
  };
}

function parseJobSkill(raw: unknown, label: string): JobSkillView {
  if (!isObject(raw) || !hasOnlyKeys(raw, JOB_SKILL_KEY_SET)) {
    throw new Error(`${label} has invalid job skill shape`);
  }
  requireKeys(raw, JOB_SKILL_KEYS, label);
  return {
    skill: parseSkillRef(raw.skill, `${label}.skill`),
    confidence: asFiniteNumber(raw.confidence, `${label}.confidence`),
    evidence: asStringList(raw.evidence, `${label}.evidence`),
  };
}

function parseJobSkillList(raw: unknown, label: string): JobSkillView[] {
  if (!Array.isArray(raw)) {
    throw new Error(`${label} must be an array`);
  }
  return raw.map((item, index) => parseJobSkill(item, `${label}[${index}]`));
}

/**
 * Strict parse of JobPostExtraction for detail views.
 * Rejects extra keys and jd_quality (not part of extraction contract).
 */
export function parseJobPostExtraction(
  raw: unknown,
): JobPostExtractionView {
  if (!isObject(raw) || !hasOnlyKeys(raw, EXTRACTION_KEY_SET)) {
    throw new Error('extraction has invalid shape or extra keys');
  }
  rejectForbiddenKeys(raw, 'extraction');
  requireKeys(raw, EXTRACTION_KEYS, 'extraction');
  const seniority = raw.seniority;
  if (
    typeof seniority !== 'string' ||
    !(JOB_SENIORITIES as readonly string[]).includes(seniority)
  ) {
    throw new Error('extraction.seniority is invalid');
  }
  const workMode = raw.work_mode;
  if (
    typeof workMode !== 'string' ||
    !(JOB_WORK_MODES as readonly string[]).includes(workMode)
  ) {
    throw new Error('extraction.work_mode is invalid');
  }
  // Extraction summary is a required string that may be empty (backend parity);
  // MatchResult.summary remains independently non-empty via parseMatchResult.
  if (typeof raw.summary !== 'string') {
    throw new Error('extraction.summary must be a string');
  }
  return {
    title: asNullableDisplayString(raw.title, 'extraction.title'),
    company: asNullableDisplayString(raw.company, 'extraction.company'),
    summary: raw.summary,
    responsibilities: asStringList(
      raw.responsibilities,
      'extraction.responsibilities',
    ),
    required_skills: parseJobSkillList(
      raw.required_skills,
      'extraction.required_skills',
    ),
    preferred_skills: parseJobSkillList(
      raw.preferred_skills,
      'extraction.preferred_skills',
    ),
    seniority: seniority as JobSeniority,
    min_experience_years: asNullableFiniteNumber(
      raw.min_experience_years,
      'extraction.min_experience_years',
    ),
    max_experience_years: asNullableFiniteNumber(
      raw.max_experience_years,
      'extraction.max_experience_years',
    ),
    location: asNullableDisplayString(raw.location, 'extraction.location'),
    work_mode: workMode as JobWorkMode,
    extraction_confidence: asFiniteNumber(
      raw.extraction_confidence,
      'extraction.extraction_confidence',
    ),
  };
}

/**
 * Strict parse of one compact SavedJobListItem.
 * Rejects prohibited redacted fields and unknown keys.
 */
export function parseSavedJobListItem(raw: unknown): SavedJobListItem {
  if (!isObject(raw) || !hasOnlyKeys(raw, SAVED_JOB_LIST_ITEM_KEY_SET)) {
    throw new Error('saved job list item has invalid shape or extra keys');
  }
  rejectForbiddenKeys(raw, 'saved job list item');
  requireKeys(raw, SAVED_JOB_LIST_ITEM_KEYS, 'saved job list item');

  const processing = raw.processing_status;
  if (
    typeof processing !== 'string' ||
    !(JOB_PROCESSING_STATUSES as readonly string[]).includes(processing)
  ) {
    throw new Error('saved job list item.processing_status is invalid');
  }

  let jdQuality: JobJdQuality | null;
  if (raw.jd_quality === null) {
    jdQuality = null;
  } else if (
    typeof raw.jd_quality === 'string' &&
    (JOB_JD_QUALITIES as readonly string[]).includes(raw.jd_quality)
  ) {
    jdQuality = raw.jd_quality as JobJdQuality;
  } else {
    throw new Error('saved job list item.jd_quality is invalid');
  }

  const sourceType = raw.source_type;
  if (
    typeof sourceType !== 'string' ||
    !(JOB_SOURCE_TYPES as readonly string[]).includes(sourceType)
  ) {
    throw new Error('saved job list item.source_type is invalid');
  }

  const evaluationState = raw.evaluation_state;
  if (
    typeof evaluationState !== 'string' ||
    !(EVALUATION_CURRENTNESS as readonly string[]).includes(evaluationState)
  ) {
    throw new Error('saved job list item.evaluation_state is invalid');
  }

  const sourceUrlRaw = asNullableDisplayString(
    raw.source_url,
    'saved job list item.source_url',
  );

  return {
    id: asNonEmptyString(raw.id, 'saved job list item.id'),
    title: asNullableDisplayString(raw.title, 'saved job list item.title'),
    company: asNullableDisplayString(
      raw.company,
      'saved job list item.company',
    ),
    processing_status: processing as JobProcessingStatus,
    jd_quality: jdQuality,
    source_type: sourceType as JobSourceType,
    source_url: safeHttpUrl(sourceUrlRaw),
    created_at: asNonEmptyString(
      raw.created_at,
      'saved job list item.created_at',
    ),
    updated_at: asNonEmptyString(
      raw.updated_at,
      'saved job list item.updated_at',
    ),
    evaluation_state: evaluationState as EvaluationCurrentness,
    latest_score: asNullableFiniteNumber(
      raw.latest_score,
      'saved job list item.latest_score',
    ),
  };
}

export function parseSavedJobListPage(raw: unknown): SavedJobListPage {
  if (!isObject(raw) || !hasOnlyKeys(raw, SAVED_JOB_LIST_PAGE_KEY_SET)) {
    throw new Error('saved job list page has invalid shape or extra keys');
  }
  rejectForbiddenKeys(raw, 'saved job list page');
  requireKeys(raw, SAVED_JOB_LIST_PAGE_KEYS, 'saved job list page');
  if (!Array.isArray(raw.items)) {
    throw new Error('saved job list page.items must be an array');
  }
  const nextCursor =
    raw.next_cursor === null
      ? null
      : asNonEmptyString(raw.next_cursor, 'saved job list page.next_cursor');
  return {
    items: raw.items.map((item, index) => {
      try {
        return parseSavedJobListItem(item);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'invalid item';
        throw new Error(`saved job list page.items[${index}]: ${msg}`);
      }
    }),
    next_cursor: nextCursor,
  };
}

/**
 * Strict parse of public JobEvaluationView; result uses MatchResult owner.
 */
export function parseJobEvaluationView(raw: unknown): JobEvaluationView {
  if (!isObject(raw) || !hasOnlyKeys(raw, JOB_EVALUATION_VIEW_KEY_SET)) {
    throw new Error('job evaluation view has invalid shape or extra keys');
  }
  rejectForbiddenKeys(raw, 'job evaluation view');
  requireKeys(raw, JOB_EVALUATION_VIEW_KEYS, 'job evaluation view');
  const evaluationState = raw.evaluation_state;
  if (
    typeof evaluationState !== 'string' ||
    !(EVALUATION_ROW_STATES as readonly string[]).includes(evaluationState)
  ) {
    throw new Error('job evaluation view.evaluation_state is invalid');
  }
  const result = parseMatchResult(raw.result);
  if (result === null) {
    throw new Error('job evaluation view.result failed MatchResult parse');
  }
  return {
    id: asNonEmptyString(raw.id, 'job evaluation view.id'),
    job_id: asNonEmptyString(raw.job_id, 'job evaluation view.job_id'),
    evaluation_state: evaluationState as EvaluationRowState,
    evaluation_context_hash: asNonEmptyString(
      raw.evaluation_context_hash,
      'job evaluation view.evaluation_context_hash',
    ),
    result,
    created_at: asNonEmptyString(
      raw.created_at,
      'job evaluation view.created_at',
    ),
    updated_at: asNonEmptyString(
      raw.updated_at,
      'job evaluation view.updated_at',
    ),
  };
}

export function parseSavedJobDetail(raw: unknown): SavedJobDetail {
  if (!isObject(raw) || !hasOnlyKeys(raw, SAVED_JOB_DETAIL_KEY_SET)) {
    throw new Error('saved job detail has invalid shape or extra keys');
  }
  for (const key of Object.keys(raw)) {
    if (
      key !== 'raw_content' &&
      key !== 'extraction' &&
      LIST_FORBIDDEN_SET.has(key)
    ) {
      throw new Error(`saved job detail must not include ${key}`);
    }
  }
  requireKeys(raw, SAVED_JOB_DETAIL_KEYS, 'saved job detail');
  const compact = parseSavedJobListItem(raw.compact);
  let extraction: JobPostExtractionView | null = null;
  if (raw.extraction !== null) {
    extraction = parseJobPostExtraction(raw.extraction);
  }
  const rawContentFinal =
    raw.raw_content === null
      ? null
      : typeof raw.raw_content === 'string'
        ? raw.raw_content
        : (() => {
            throw new Error(
              'saved job detail.raw_content must be string or null',
            );
          })();
  let latestEvaluation: JobEvaluationView | null = null;
  if (raw.latest_evaluation !== null) {
    latestEvaluation = parseJobEvaluationView(raw.latest_evaluation);
  }
  return {
    compact,
    extraction,
    raw_content: rawContentFinal,
    latest_evaluation: latestEvaluation,
  };
}

export function parseEvaluateJobResponse(raw: unknown): EvaluateJobResponse {
  if (!isObject(raw) || !hasOnlyKeys(raw, EVALUATE_RESPONSE_KEY_SET)) {
    throw new Error('evaluate response has invalid shape or extra keys');
  }
  rejectForbiddenKeys(raw, 'evaluate response');
  requireKeys(raw, EVALUATE_RESPONSE_KEYS, 'evaluate response');
  const outcome = raw.outcome;
  if (
    typeof outcome !== 'string' ||
    !(EVALUATE_OUTCOMES as readonly string[]).includes(outcome)
  ) {
    throw new Error('evaluate response.outcome is invalid');
  }
  return {
    outcome: outcome as EvaluateOutcome,
    job: parseSavedJobListItem(raw.job),
    evaluation: parseJobEvaluationView(raw.evaluation),
  };
}

export function parseSaveAndEvaluateResponse(
  raw: unknown,
): SaveAndEvaluateResponse {
  if (!isObject(raw) || !hasOnlyKeys(raw, SAVE_AND_EVALUATE_RESPONSE_KEY_SET)) {
    throw new Error(
      'save-and-evaluate response has invalid shape or extra keys',
    );
  }
  rejectForbiddenKeys(raw, 'save-and-evaluate response');
  requireKeys(
    raw,
    SAVE_AND_EVALUATE_RESPONSE_KEYS,
    'save-and-evaluate response',
  );
  const ingest = raw.ingest_outcome;
  if (
    typeof ingest !== 'string' ||
    !(SAVE_INGEST_OUTCOMES as readonly string[]).includes(ingest)
  ) {
    throw new Error('save-and-evaluate response.ingest_outcome is invalid');
  }
  const evalOutcome = raw.evaluation_outcome;
  if (
    typeof evalOutcome !== 'string' ||
    !(SAVE_EVALUATION_OUTCOMES as readonly string[]).includes(evalOutcome)
  ) {
    throw new Error(
      'save-and-evaluate response.evaluation_outcome is invalid',
    );
  }
  const code =
    raw.code === null
      ? null
      : asNonEmptyString(raw.code, 'save-and-evaluate response.code');
  let evaluation: JobEvaluationView | null = null;
  if (raw.evaluation !== null) {
    evaluation = parseJobEvaluationView(raw.evaluation);
  }
  if (evalOutcome === 'unavailable' && evaluation !== null) {
    throw new Error(
      'save-and-evaluate unavailable must not include evaluation',
    );
  }
  if (
    (evalOutcome === 'created' || evalOutcome === 'reused') &&
    evaluation === null
  ) {
    throw new Error('save-and-evaluate created/reused requires evaluation');
  }
  return {
    ingest_outcome: ingest as SaveIngestOutcome,
    job: parseSavedJobListItem(raw.job),
    evaluation_outcome: evalOutcome as SaveEvaluationOutcome,
    evaluation,
    code,
  };
}

/**
 * Strict parse of ReextractJobResponse.
 * sync_ok=true requires null code and rebuild_instruction.
 * sync_ok=false requires code=NEO4J_SYNC_FAILED and non-blank rebuild guidance.
 * Never coerces malformed sync/code/rebuild combinations.
 */
export function parseReextractJobResponse(raw: unknown): ReextractJobResponse {
  if (!isObject(raw) || !hasOnlyKeys(raw, REEXTRACT_RESPONSE_KEY_SET)) {
    throw new Error('reextract response has invalid shape or extra keys');
  }
  rejectForbiddenKeys(raw, 'reextract response');
  requireKeys(raw, REEXTRACT_RESPONSE_KEYS, 'reextract response');

  const outcome = raw.outcome;
  if (
    typeof outcome !== 'string' ||
    !(REEXTRACT_OUTCOMES as readonly string[]).includes(outcome)
  ) {
    throw new Error('reextract response.outcome is invalid');
  }

  if (typeof raw.sync_ok !== 'boolean') {
    throw new Error('reextract response.sync_ok must be a boolean');
  }
  const syncOk = raw.sync_ok;

  // code and rebuild_instruction are required keys; null is valid only for sync_ok=true.
  if (!Object.prototype.hasOwnProperty.call(raw, 'code')) {
    throw new Error('reextract response missing required key code');
  }
  if (!Object.prototype.hasOwnProperty.call(raw, 'rebuild_instruction')) {
    throw new Error(
      'reextract response missing required key rebuild_instruction',
    );
  }

  let code: string | null;
  if (raw.code === null) {
    code = null;
  } else if (typeof raw.code === 'string' && raw.code.trim() !== '') {
    code = raw.code;
  } else {
    throw new Error('reextract response.code must be string or null');
  }

  let rebuildInstruction: string | null;
  if (raw.rebuild_instruction === null) {
    rebuildInstruction = null;
  } else if (
    typeof raw.rebuild_instruction === 'string' &&
    raw.rebuild_instruction.trim() !== ''
  ) {
    rebuildInstruction = raw.rebuild_instruction;
  } else if (typeof raw.rebuild_instruction === 'string') {
    throw new Error(
      'reextract response.rebuild_instruction must be non-blank when present',
    );
  } else {
    throw new Error(
      'reextract response.rebuild_instruction must be string or null',
    );
  }

  if (syncOk) {
    if (code !== null || rebuildInstruction !== null) {
      throw new Error(
        'reextract response sync_ok=true requires code and rebuild_instruction to be null',
      );
    }
  } else {
    if (code !== REEXTRACT_GRAPH_FAILURE_CODE) {
      throw new Error(
        "reextract response sync_ok=false requires code='NEO4J_SYNC_FAILED'",
      );
    }
    if (rebuildInstruction === null) {
      throw new Error(
        'reextract response sync_ok=false requires non-blank rebuild_instruction',
      );
    }
  }

  return {
    outcome: outcome as ReextractOutcome,
    job: parseSavedJobListItem(raw.job),
    sync_ok: syncOk,
    code,
    rebuild_instruction: rebuildInstruction,
  };
}

/**
 * Prefer preserved selection when still present; else first remaining row
 * (newest-first list order). Deterministic post-delete selection.
 */
export function selectSafeRemainingJobId(
  items: ReadonlyArray<{id: string}>,
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
  return remaining[0]?.id ?? null;
}

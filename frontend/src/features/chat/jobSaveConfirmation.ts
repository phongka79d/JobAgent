/**
 * Strict job_save_confirmation pending-projection parser and row selector.
 * Sole vocabulary owner for passive-JD approval (Plan 12 / Master §15.7).
 * Reuses stream/history row association; no second store or resume transport.
 */

import {isSaveJobToolName, parseSaveJobResultData} from '../jobs/types';
import type {
  ClientMessage,
  ClientRun,
} from './model';
import type {HistoryPage, JsonObject, JsonValue} from './types';

export const JOB_SAVE_CONFIRMATION_KIND = 'job_save_confirmation' as const;
export const SAVE_JOB_ACTION = 'save_job' as const;
export const CANCEL_SAVE_JOB_ACTION = 'cancel_save_job' as const;

export type JobSaveConfirmationAction =
  | typeof SAVE_JOB_ACTION
  | typeof CANCEL_SAVE_JOB_ACTION;

export const SAVE_JOB_LABEL = 'Lưu JD';
export const CANCEL_SAVE_JOB_LABEL = 'Không lưu';
export const JD_CONFIRMATION_HEADING = 'Đã nhận diện nội dung JD';
export const JD_CONFIRMATION_SENTENCE =
  'JD này chưa được lưu. Bạn có muốn lưu JD này không?';
export const REVIEW_JD_LABEL = 'Review JD';

export const CURRENT_MESSAGE_SOURCE = 'current_message' as const;
export const TEXT_LENGTH_MIN = 1;
export const TEXT_LENGTH_MAX = 1_000_000;
export const PREVIEW_TITLE_MAX = 160;
export const PREVIEW_SKILL_MAX = 80;
export const PREVIEW_SKILLS_MAX = 5;

/** Exact resume actions required for a valid JD confirmation. */
const TOP_LEVEL_ALLOWED = new Set(['kind', 'allowed_actions', 'card']);
const CARD_ALLOWED = new Set([
  'tool_name',
  'tool_call_id',
  'source',
  'text_length',
  'preview',
]);
const PREVIEW_ALLOWED = new Set(['title', 'company', 'skills']);

/**
 * Forbidden keys at projection / card / preview levels.
 * Any presence invalidates the entire JD card (no coercion).
 */
const FORBIDDEN_KEYS = new Set([
  'text',
  'raw_content',
  'message_id',
  'user_message_id',
  'url',
  'source_url',
  'hash',
  'arguments',
  'prompt',
  'credential',
  'provider',
  'stack',
]);

export type JobSaveConfirmationPreview = {
  title: string | null;
  company: string | null;
  skills: readonly string[];
};

export type JobSaveConfirmationCardData = {
  toolName: typeof SAVE_JOB_ACTION;
  toolCallId: string;
  source: typeof CURRENT_MESSAGE_SOURCE;
  textLength: number;
  preview: JobSaveConfirmationPreview;
};

export type JobSaveConfirmationProjection = {
  kind: typeof JOB_SAVE_CONFIRMATION_KIND;
  allowedActions: readonly JobSaveConfirmationAction[];
  card: JobSaveConfirmationCardData;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasForbiddenKey(obj: Record<string, unknown>): boolean {
  for (const key of Object.keys(obj)) {
    if (FORBIDDEN_KEYS.has(key)) {
      return true;
    }
  }
  return false;
}

function hasOnlyAllowedKeys(
  obj: Record<string, unknown>,
  allowed: ReadonlySet<string>,
): boolean {
  for (const key of Object.keys(obj)) {
    if (!allowed.has(key)) {
      return false;
    }
  }
  return true;
}

function asNonEmptyBoundedString(
  value: JsonValue | undefined,
  maxLen: number,
): string | null | undefined {
  // undefined = missing key path handled by caller; null is allowed.
  if (value === null) {
    return null;
  }
  if (typeof value !== 'string') {
    return undefined;
  }
  if (value.trim() === '' || value.length > maxLen) {
    return undefined;
  }
  return value;
}

function parsePreview(
  raw: unknown,
): JobSaveConfirmationPreview | null {
  if (!isObject(raw)) {
    return null;
  }
  if (hasForbiddenKey(raw) || !hasOnlyAllowedKeys(raw, PREVIEW_ALLOWED)) {
    return null;
  }
  if (
    !Object.prototype.hasOwnProperty.call(raw, 'title') ||
    !Object.prototype.hasOwnProperty.call(raw, 'company') ||
    !Object.prototype.hasOwnProperty.call(raw, 'skills')
  ) {
    return null;
  }

  const title = asNonEmptyBoundedString(
    raw.title as JsonValue,
    PREVIEW_TITLE_MAX,
  );
  if (title === undefined) {
    return null;
  }
  const company = asNonEmptyBoundedString(
    raw.company as JsonValue,
    PREVIEW_TITLE_MAX,
  );
  if (company === undefined) {
    return null;
  }

  if (!Array.isArray(raw.skills)) {
    return null;
  }
  if (raw.skills.length > PREVIEW_SKILLS_MAX) {
    return null;
  }
  const skills: string[] = [];
  for (const skill of raw.skills) {
    if (typeof skill !== 'string' || skill.trim() === '') {
      return null;
    }
    if (skill.length > PREVIEW_SKILL_MAX) {
      return null;
    }
    skills.push(skill);
  }

  return {title, company, skills};
}

/**
 * True only when kind and allowed_actions are exactly the JD confirmation pair
 * (no missing, extra, or duplicate actions).
 */
export function isJobSaveConfirmationApproval(
  kind: string | null | undefined,
  allowedActions: readonly string[] | null | undefined,
): boolean {
  if (kind !== JOB_SAVE_CONFIRMATION_KIND) {
    return false;
  }
  if (!allowedActions || allowedActions.length !== 2) {
    return false;
  }
  const [a, b] = allowedActions;
  if (typeof a !== 'string' || typeof b !== 'string') {
    return false;
  }
  if (a === b) {
    return false;
  }
  const set = new Set(allowedActions);
  return (
    set.size === 2 &&
    set.has(SAVE_JOB_ACTION) &&
    set.has(CANCEL_SAVE_JOB_ACTION)
  );
}

/**
 * Parse durable pending_approval / SSE payload into a strict JD projection.
 * Returns null for any missing/extra/wrong-type/over-limit/forbidden field.
 * Never coerces invalid data into a card.
 */
export function parseJobSaveConfirmationProjection(
  pending: JsonObject | null | undefined,
): JobSaveConfirmationProjection | null {
  if (!pending || !isObject(pending)) {
    return null;
  }
  if (hasForbiddenKey(pending) || !hasOnlyAllowedKeys(pending, TOP_LEVEL_ALLOWED)) {
    return null;
  }

  const kind =
    typeof pending.kind === 'string' && pending.kind.trim() !== ''
      ? pending.kind
      : null;
  if (kind !== JOB_SAVE_CONFIRMATION_KIND) {
    return null;
  }

  const allowedRaw = pending.allowed_actions;
  if (!Array.isArray(allowedRaw)) {
    return null;
  }
  const allowedActions = allowedRaw.filter(
    (a): a is string => typeof a === 'string',
  );
  if (allowedActions.length !== allowedRaw.length) {
    return null;
  }
  if (!isJobSaveConfirmationApproval(kind, allowedActions)) {
    return null;
  }

  if (!isObject(pending.card)) {
    return null;
  }
  const cardRaw = pending.card;
  if (hasForbiddenKey(cardRaw) || !hasOnlyAllowedKeys(cardRaw, CARD_ALLOWED)) {
    return null;
  }

  if (cardRaw.tool_name !== SAVE_JOB_ACTION) {
    return null;
  }
  if (
    typeof cardRaw.tool_call_id !== 'string' ||
    cardRaw.tool_call_id.trim() === ''
  ) {
    return null;
  }
  if (cardRaw.source !== CURRENT_MESSAGE_SOURCE) {
    return null;
  }
  if (
    typeof cardRaw.text_length !== 'number' ||
    !Number.isInteger(cardRaw.text_length) ||
    cardRaw.text_length < TEXT_LENGTH_MIN ||
    cardRaw.text_length > TEXT_LENGTH_MAX
  ) {
    return null;
  }

  const preview = parsePreview(cardRaw.preview);
  if (!preview) {
    return null;
  }

  return {
    kind: JOB_SAVE_CONFIRMATION_KIND,
    allowedActions: allowedActions as JobSaveConfirmationAction[],
    card: {
      toolName: SAVE_JOB_ACTION,
      toolCallId: cardRaw.tool_call_id,
      source: CURRENT_MESSAGE_SOURCE,
      textLength: cardRaw.text_length,
      preview,
    },
  };
}

/**
 * Resolve the interrupted job_save_confirmation run for a message row.
 * Stream path: own run. History path: assistant hosts preceding user.run.
 * Same association rules as profileCommitForRow; never crosses run/message boundaries.
 */
export function jobSaveConfirmationForRow(
  messages: readonly ClientMessage[],
  index: number,
): {run: ClientRun; projection: JobSaveConfirmationProjection} | null {
  const message = messages[index];
  if (!message) {
    return null;
  }

  const tryRun = (run: ClientRun | null | undefined) => {
    if (!run || run.state !== 'interrupted' || !run.pendingApproval) {
      return null;
    }
    const projection = parseJobSaveConfirmationProjection(run.pendingApproval);
    if (!projection) {
      return null;
    }
    return {run, projection};
  };

  const own = tryRun(message.run);
  if (own) {
    if (message.role === 'assistant') {
      return own;
    }
    if (message.role === 'user') {
      const next = messages[index + 1];
      if (next?.role === 'assistant') {
        // Prefer the following assistant host when present (exact-one card).
        return null;
      }
      return own;
    }
  }

  if (message.role === 'assistant') {
    for (let i = index - 1; i >= 0; i -= 1) {
      const prev = messages[i];
      if (prev.role === 'user') {
        return tryRun(prev.run);
      }
      if (prev.role === 'assistant') {
        return null;
      }
    }
  }
  return null;
}

/**
 * Durable history proof: this run has a validated save_job ToolResult with
 * sqlite_committed=true. Used only after terminal rehydrate for invalidation.
 */
export function historyPageHasCommittedSaveJob(
  page: HistoryPage,
  runId: string,
): boolean {
  for (const item of page.items) {
    const run = item.run;
    if (!run || run.id !== runId) {
      continue;
    }
    for (const tool of run.tool_executions) {
      if (!isSaveJobToolName(tool.tool_name)) {
        continue;
      }
      if (tool.status !== 'completed' || tool.error_code) {
        continue;
      }
      const data = tool.result?.data ?? null;
      const parsed = parseSaveJobResultData(
        data !== null && isObject(data) ? (data as JsonObject) : null,
      );
      if (parsed?.sqliteCommitted === true) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Presentation-only: running/pending save_job under a valid JD interrupt.
 */
export function shouldLabelReviewJd(
  toolName: string,
  status: string,
  reviewJdActive: boolean,
): boolean {
  return (
    reviewJdActive &&
    toolName === SAVE_JOB_ACTION &&
    (status === 'running' || status === 'pending')
  );
}

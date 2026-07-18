/**
 * Strict durable read_active_cv evidence projection and row-level selector
 * (Plan 12 — Strict Active-CV Evidence Projection / Evidence Binding).
 *
 * Single vocabulary owner for valid pages and entry/chunk records.
 * Reuses isUuidV4 and JSON types; does not create a general validation framework.
 * Stream tool_status keeps resultData=null; only terminal history supplies evidence.
 */

import type {ClientToolActivity} from './reducer';
import type {JsonObject} from './types';
import {isUuidV4} from './types';

export const READ_ACTIVE_CV_TOOL_NAME = 'read_active_cv' as const;

export const ACTIVE_CV_MODES = ['section', 'search', 'chunk'] as const;
export type ActiveCvMode = (typeof ACTIVE_CV_MODES)[number];

export const ACTIVE_CV_ENTRY_KINDS = ['entry', 'entry_match'] as const;
export type ActiveCvEntryKind = (typeof ACTIVE_CV_ENTRY_KINDS)[number];

export const ACTIVE_CV_CHUNK_KINDS = ['chunk', 'chunk_match'] as const;
export type ActiveCvChunkKind = (typeof ACTIVE_CV_CHUNK_KINDS)[number];

export type ActiveCvRecordKind = ActiveCvEntryKind | ActiveCvChunkKind;

/** Per-page result and character ceilings (backend / Master §13.7). */
export const ACTIVE_CV_MAX_RECORDS = 10;
export const ACTIVE_CV_MAX_RETURNED_CHARS = 12_000;

const PAGE_KEYS = [
  'attachment_id',
  'extraction_version',
  'source_hash',
  'mode',
  'returned_chars',
  'truncated',
  'has_more',
  'records',
] as const;

const MODE_SET: ReadonlySet<string> = new Set(ACTIVE_CV_MODES);
const ENTRY_KIND_SET: ReadonlySet<string> = new Set(ACTIVE_CV_ENTRY_KINDS);
const CHUNK_KIND_SET: ReadonlySet<string> = new Set(ACTIVE_CV_CHUNK_KINDS);

export type ActiveCvEntryRecord = {
  kind: ActiveCvEntryKind;
  section_id: string;
  entry_id: string;
  ordinal: number;
  title: string | null;
  subtitle: string | null;
  date_text: string | null;
  location: string | null;
  body: string;
  bullets: string[];
  source_chunk_ordinals: number[];
  excerpt?: string;
  record_truncated?: boolean;
};

export type ActiveCvChunkRecord = {
  kind: ActiveCvChunkKind;
  ordinal: number;
  text: string;
  char_count: number;
  excerpt?: string;
  record_truncated?: boolean;
};

export type ActiveCvRecord = ActiveCvEntryRecord | ActiveCvChunkRecord;

/** One projected successful read_active_cv page (cursor discarded). */
export type ActiveCvPage = {
  attachment_id: string;
  extraction_version: string;
  source_hash: string | null;
  mode: ActiveCvMode;
  returned_chars: number;
  truncated: boolean;
  has_more: boolean;
  records: ActiveCvRecord[];
};

/**
 * Row-bound evidence bundle: one consistent CV revision across ordered pages.
 * Attachment/extraction/source fields are the shared revision key.
 */
export type ActiveCvEvidenceBundle = {
  attachment_id: string;
  extraction_version: string;
  source_hash: string | null;
  pages: ActiveCvPage[];
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonNegativeInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isBoundedReturnedChars(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= 0 &&
    value <= ACTIVE_CV_MAX_RETURNED_CHARS
  );
}

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') {
    return null;
  }
  return value;
}

function asNullableString(value: unknown): string | null | undefined {
  if (value === null) {
    return null;
  }
  if (typeof value === 'string') {
    return value;
  }
  return undefined;
}

function parseStringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const out: string[] = [];
  for (const item of value) {
    if (typeof item !== 'string') {
      return null;
    }
    out.push(item);
  }
  return out;
}

function parseNonNegativeIntList(value: unknown): number[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const out: number[] = [];
  for (const item of value) {
    if (!isNonNegativeInt(item)) {
      return null;
    }
    out.push(item);
  }
  return out;
}

function parseOptionalExcerpt(
  raw: Record<string, unknown>,
  target: {excerpt?: string},
): boolean {
  if (!Object.prototype.hasOwnProperty.call(raw, 'excerpt')) {
    return true;
  }
  if (typeof raw.excerpt !== 'string') {
    return false;
  }
  target.excerpt = raw.excerpt;
  return true;
}

function parseOptionalRecordTruncated(
  raw: Record<string, unknown>,
  target: {record_truncated?: boolean},
): boolean {
  if (!Object.prototype.hasOwnProperty.call(raw, 'record_truncated')) {
    return true;
  }
  if (typeof raw.record_truncated !== 'boolean') {
    return false;
  }
  target.record_truncated = raw.record_truncated;
  return true;
}

function parseEntryRecord(raw: Record<string, unknown>): ActiveCvEntryRecord | null {
  const kind = raw.kind;
  if (typeof kind !== 'string' || !ENTRY_KIND_SET.has(kind)) {
    return null;
  }
  const sectionId = asNonEmptyString(raw.section_id);
  const entryId = asNonEmptyString(raw.entry_id);
  if (sectionId === null || entryId === null) {
    return null;
  }
  if (!isNonNegativeInt(raw.ordinal)) {
    return null;
  }
  const title = asNullableString(raw.title);
  const subtitle = asNullableString(raw.subtitle);
  const dateText = asNullableString(raw.date_text);
  const location = asNullableString(raw.location);
  if (
    title === undefined ||
    subtitle === undefined ||
    dateText === undefined ||
    location === undefined
  ) {
    return null;
  }
  if (typeof raw.body !== 'string') {
    return null;
  }
  const bullets = parseStringList(raw.bullets);
  if (bullets === null) {
    return null;
  }
  const sourceChunkOrdinals = parseNonNegativeIntList(raw.source_chunk_ordinals);
  if (sourceChunkOrdinals === null) {
    return null;
  }

  const record: ActiveCvEntryRecord = {
    kind: kind as ActiveCvEntryKind,
    section_id: sectionId,
    entry_id: entryId,
    ordinal: raw.ordinal,
    title,
    subtitle,
    date_text: dateText,
    location,
    body: raw.body,
    bullets,
    source_chunk_ordinals: sourceChunkOrdinals,
  };
  if (!parseOptionalExcerpt(raw, record)) {
    return null;
  }
  if (!parseOptionalRecordTruncated(raw, record)) {
    return null;
  }
  return record;
}

function parseChunkRecord(raw: Record<string, unknown>): ActiveCvChunkRecord | null {
  const kind = raw.kind;
  if (typeof kind !== 'string' || !CHUNK_KIND_SET.has(kind)) {
    return null;
  }
  if (!isNonNegativeInt(raw.ordinal)) {
    return null;
  }
  if (typeof raw.text !== 'string') {
    return null;
  }
  if (!isNonNegativeInt(raw.char_count)) {
    return null;
  }

  const record: ActiveCvChunkRecord = {
    kind: kind as ActiveCvChunkKind,
    ordinal: raw.ordinal,
    text: raw.text,
    char_count: raw.char_count,
  };
  if (!parseOptionalExcerpt(raw, record)) {
    return null;
  }
  if (!parseOptionalRecordTruncated(raw, record)) {
    return null;
  }
  return record;
}

function parseRecord(value: unknown): ActiveCvRecord | null {
  if (!isObject(value)) {
    return null;
  }
  const kind = value.kind;
  if (typeof kind !== 'string') {
    return null;
  }
  if (ENTRY_KIND_SET.has(kind)) {
    return parseEntryRecord(value);
  }
  if (CHUNK_KIND_SET.has(kind)) {
    return parseChunkRecord(value);
  }
  return null;
}

function entryToJson(record: ActiveCvEntryRecord): JsonObject {
  const out: JsonObject = {
    kind: record.kind,
    section_id: record.section_id,
    entry_id: record.entry_id,
    ordinal: record.ordinal,
    title: record.title,
    subtitle: record.subtitle,
    date_text: record.date_text,
    location: record.location,
    body: record.body,
    bullets: record.bullets,
    source_chunk_ordinals: record.source_chunk_ordinals,
  };
  if (record.excerpt !== undefined) {
    out.excerpt = record.excerpt;
  }
  if (record.record_truncated !== undefined) {
    out.record_truncated = record.record_truncated;
  }
  return out;
}

function chunkToJson(record: ActiveCvChunkRecord): JsonObject {
  const out: JsonObject = {
    kind: record.kind,
    ordinal: record.ordinal,
    text: record.text,
    char_count: record.char_count,
  };
  if (record.excerpt !== undefined) {
    out.excerpt = record.excerpt;
  }
  if (record.record_truncated !== undefined) {
    out.record_truncated = record.record_truncated;
  }
  return out;
}

function recordToJson(record: ActiveCvRecord): JsonObject {
  if (ENTRY_KIND_SET.has(record.kind)) {
    return entryToJson(record as ActiveCvEntryRecord);
  }
  return chunkToJson(record as ActiveCvChunkRecord);
}

function pageToJson(page: ActiveCvPage): JsonObject {
  return {
    attachment_id: page.attachment_id,
    extraction_version: page.extraction_version,
    source_hash: page.source_hash,
    mode: page.mode,
    returned_chars: page.returned_chars,
    truncated: page.truncated,
    has_more: page.has_more,
    records: page.records.map(recordToJson),
  };
}

/**
 * Strict parse of durable ToolResult.data for one read_active_cv page.
 * Derives has_more from non-null next_cursor; rejects required vocabulary failures.
 */
export function parseActiveCvPageData(
  data: JsonObject | null | undefined,
): ActiveCvPage | null {
  if (!isObject(data)) {
    return null;
  }

  const attachmentId = data.attachment_id;
  if (typeof attachmentId !== 'string' || !isUuidV4(attachmentId)) {
    return null;
  }

  const extractionVersion = asNonEmptyString(data.extraction_version);
  if (extractionVersion === null) {
    return null;
  }

  if (!Object.prototype.hasOwnProperty.call(data, 'source_hash')) {
    return null;
  }
  const sourceHash = asNullableString(data.source_hash);
  if (sourceHash === undefined) {
    return null;
  }

  const mode = data.mode;
  if (typeof mode !== 'string' || !MODE_SET.has(mode)) {
    return null;
  }

  if (!isBoundedReturnedChars(data.returned_chars)) {
    return null;
  }

  if (typeof data.truncated !== 'boolean') {
    return null;
  }

  // has_more is derived from next_cursor when projecting; if already projected,
  // accept a boolean has_more (cursor must be absent).
  let hasMore: boolean;
  if (Object.prototype.hasOwnProperty.call(data, 'next_cursor')) {
    const cursor = data.next_cursor;
    if (cursor === null) {
      hasMore = false;
    } else if (typeof cursor === 'string') {
      hasMore = true;
    } else {
      return null;
    }
  } else if (typeof data.has_more === 'boolean') {
    hasMore = data.has_more;
  } else {
    return null;
  }

  if (!Array.isArray(data.records)) {
    return null;
  }
  if (
    data.records.length < 1 ||
    data.records.length > ACTIVE_CV_MAX_RECORDS
  ) {
    return null;
  }

  const records: ActiveCvRecord[] = [];
  for (const item of data.records) {
    const parsed = parseRecord(item);
    if (parsed === null) {
      return null;
    }
    records.push(parsed);
  }

  return {
    attachment_id: attachmentId,
    extraction_version: extractionVersion,
    source_hash: sourceHash,
    mode: mode as ActiveCvMode,
    returned_chars: data.returned_chars,
    truncated: data.truncated,
    has_more: hasMore,
    records,
  };
}

/**
 * Durable history boundary projection for read_active_cv ToolResult.data.
 * Allowlists page + record fields; derives has_more; strips next_cursor and
 * all unknown/forbidden keys. Unrelated tools return null for chain callers.
 */
export function projectActiveCvResultData(
  toolName: string,
  data: JsonObject | null | undefined,
): JsonObject | null {
  if (toolName !== READ_ACTIVE_CV_TOOL_NAME) {
    return null;
  }
  const page = parseActiveCvPageData(data);
  if (page === null) {
    return null;
  }
  // Re-parse the slim JSON to guarantee only approved keys survive.
  const slim = pageToJson(page);
  if (parseActiveCvPageData(slim) === null) {
    return null;
  }
  // Belt: ensure next_cursor and non-PAGE_KEYS never appear.
  for (const key of Object.keys(slim)) {
    if (!(PAGE_KEYS as readonly string[]).includes(key)) {
      return null;
    }
  }
  return slim;
}

export function isReadActiveCvToolName(toolName: string): boolean {
  return toolName === READ_ACTIVE_CV_TOOL_NAME;
}

/**
 * Select successful durable read_active_cv pages from an assistant-row tool
 * association (toolsForAssistantDisplay output). Returns a bundle only when at
 * least one valid page exists and all valid pages agree on revision identity.
 * Failed/malformed pages are ignored when another valid page exists; conflicting
 * valid revisions suppress the entire bundle.
 */
export function activeCvEvidenceForTools(
  tools: readonly ClientToolActivity[],
): ActiveCvEvidenceBundle | null {
  const pages: ActiveCvPage[] = [];

  for (const tool of tools) {
    if (tool.toolName !== READ_ACTIVE_CV_TOOL_NAME) {
      continue;
    }
    if (tool.status !== 'completed') {
      continue;
    }
    if (tool.errorCode !== null && tool.errorCode !== undefined) {
      continue;
    }
    const page = parseActiveCvPageData(tool.resultData);
    if (page === null) {
      // Malformed / empty / failed projection — ignore if another valid page exists.
      continue;
    }
    pages.push(page);
  }

  if (pages.length === 0) {
    return null;
  }

  const attachmentId = pages[0].attachment_id;
  const extractionVersion = pages[0].extraction_version;
  const sourceHash = pages[0].source_hash;
  for (let i = 1; i < pages.length; i += 1) {
    const page = pages[i];
    if (
      page.attachment_id !== attachmentId ||
      page.extraction_version !== extractionVersion ||
      page.source_hash !== sourceHash
    ) {
      // Conflicting valid revisions → suppress whole evidence bundle.
      return null;
    }
  }

  return {
    attachment_id: attachmentId,
    extraction_version: extractionVersion,
    source_hash: sourceHash,
    pages,
  };
}

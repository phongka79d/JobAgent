/**
 * Typed observability read contracts (Plan 8).
 * Mirrors backend schemas/observability.py — never PDF bytes, storage paths,
 * prompts, checkpoints, tool arguments, embeddings, or secrets.
 */

import {
  RUN_STATES,
  TOOL_STATUSES,
  type RunState,
  type ToolStatus,
} from '../chat/types';

export type ObservabilityAttachmentState =
  | 'staged'
  | 'active'
  | 'archived'
  | 'failed';

export type GraphStatus = 'ready' | 'stale' | 'unavailable';

export type GraphEdgeType =
  | 'HAS_SKILL'
  | 'REQUIRES'
  | 'PREFERS'
  | 'RELATED_TO';

export type ObservabilityTabId =
  | 'overview'
  | 'cv-history'
  | 'chunks'
  | 'graph'
  | 'runs';

export type CvHistoryItem = {
  id: string;
  original_name: string;
  mime_type: 'application/pdf';
  size_bytes: number;
  page_count: number | null;
  state: ObservabilityAttachmentState;
  failure_code: string | null;
  file_hash_abbreviated: string;
  file_available: boolean;
  created_at: string;
  updated_at: string;
};

export type CvHistoryPage = {
  items: CvHistoryItem[];
  next_cursor: string | null;
};

export type ChunkListItem = {
  attachment_id: string;
  ordinal: number;
  preview: string;
  char_count: number;
  token_estimate: number;
  created_at: string;
};

export type ChunkListPage = {
  items: ChunkListItem[];
  next_cursor: string | null;
};

export type ChunkDetail = {
  attachment_id: string;
  ordinal: number;
  text: string;
  preview: string;
  char_count: number;
  token_estimate: number;
  created_at: string;
};

export type ObservabilityToolExecution = {
  id: string;
  tool_name: string;
  status: ToolStatus;
  duration_ms: number | null;
  error_code: string | null;
  summary: string | null;
};

export type RunHistoryItem = {
  id: string;
  user_message_id: string;
  state: RunState;
  error_code: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  related_attachment_ids: string[];
  related_job_ids: string[];
  tool_executions: ObservabilityToolExecution[];
};

export type RunHistoryPage = {
  items: RunHistoryItem[];
  next_cursor: string | null;
};

export type GraphCandidateNode = {
  id: string;
  revision: string;
};

export type GraphJobNode = {
  id: string;
  title: string;
  company: string;
  revision: string;
};

export type GraphSkillNode = {
  canonical_name: string;
};

export type GraphEdge = {
  source_id: string;
  target_id: string;
  type: GraphEdgeType;
};

export type GraphSnapshot = {
  status: GraphStatus;
  code: string | null;
  summary: string;
  rebuild_instruction: string | null;
  candidate: GraphCandidateNode | null;
  jobs: GraphJobNode[];
  skills: GraphSkillNode[];
  edges: GraphEdge[];
  nodes_truncated: boolean;
  edges_truncated: boolean;
  omitted_node_count: number;
  omitted_edge_count: number;
  checked_at: string;
};

export type ObservabilitySafeError = {
  code: string;
  summary: string;
};

const ATTACHMENT_STATES: ReadonlySet<string> = new Set([
  'staged',
  'active',
  'archived',
  'failed',
]);

const GRAPH_STATUSES: ReadonlySet<string> = new Set([
  'ready',
  'stale',
  'unavailable',
]);

const GRAPH_EDGE_TYPES: ReadonlySet<string> = new Set([
  'HAS_SKILL',
  'REQUIRES',
  'PREFERS',
  'RELATED_TO',
]);

const FORBIDDEN_KEYS: ReadonlySet<string> = new Set([
  'storage_path',
  'file_hash',
  'embedding',
  'embeddings',
  'checkpoint',
  'prompt',
  'arguments_summary',
  'arguments_summary_json',
  'pending_approval',
  'pending_approval_json',
  'api_key',
  'SHOPAIKEY_API_KEY',
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function rejectForbiddenKeys(raw: Record<string, unknown>, label: string): void {
  for (const key of Object.keys(raw)) {
    if (FORBIDDEN_KEYS.has(key)) {
      throw new Error(`${label} must not include ${key}`);
    }
  }
}

function requireString(
  raw: Record<string, unknown>,
  key: string,
  label: string,
): string {
  const value = asString(raw[key]);
  if (!value) {
    throw new Error(`${label}.${key} must be a non-empty string`);
  }
  return value;
}

function optionalString(
  raw: Record<string, unknown>,
  key: string,
  label: string,
): string | null {
  if (raw[key] === null || raw[key] === undefined) {
    return null;
  }
  const value = asString(raw[key]);
  if (value === null) {
    throw new Error(`${label}.${key} must be string or null`);
  }
  return value;
}

function requireNonNegInt(
  raw: Record<string, unknown>,
  key: string,
  label: string,
): number {
  const value = asNumber(raw[key]);
  if (value === null || !Number.isInteger(value) || value < 0) {
    throw new Error(`${label}.${key} must be a non-negative integer`);
  }
  return value;
}

function parseStringList(
  value: unknown,
  label: string,
): string[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be an array`);
  }
  return value.map((item, index) => {
    if (typeof item !== 'string' || item === '') {
      throw new Error(`${label}[${index}] must be a non-empty string`);
    }
    return item;
  });
}

export function parseCvHistoryItem(raw: unknown): CvHistoryItem {
  if (!isObject(raw)) {
    throw new Error('cv history item must be an object');
  }
  rejectForbiddenKeys(raw, 'cv history item');
  const id = requireString(raw, 'id', 'cv history item');
  const original_name = requireString(raw, 'original_name', 'cv history item');
  const mime_type = asString(raw.mime_type);
  if (mime_type !== 'application/pdf') {
    throw new Error('cv history item.mime_type must be application/pdf');
  }
  const size_bytes = asNumber(raw.size_bytes);
  if (size_bytes === null || size_bytes <= 0) {
    throw new Error('cv history item.size_bytes must be a positive number');
  }
  const state = asString(raw.state);
  if (!state || !ATTACHMENT_STATES.has(state)) {
    throw new Error('cv history item.state is invalid');
  }
  const file_available = asBoolean(raw.file_available);
  if (file_available === null) {
    throw new Error('cv history item.file_available must be boolean');
  }
  const pageRaw = raw.page_count;
  const page_count =
    pageRaw === null || pageRaw === undefined ? null : asNumber(pageRaw);
  if (pageRaw !== null && pageRaw !== undefined && page_count === null) {
    throw new Error('cv history item.page_count must be number or null');
  }
  return {
    id,
    original_name,
    mime_type: 'application/pdf',
    size_bytes,
    page_count,
    state: state as ObservabilityAttachmentState,
    failure_code: optionalString(raw, 'failure_code', 'cv history item'),
    file_hash_abbreviated: requireString(
      raw,
      'file_hash_abbreviated',
      'cv history item',
    ),
    file_available,
    created_at: requireString(raw, 'created_at', 'cv history item'),
    updated_at: requireString(raw, 'updated_at', 'cv history item'),
  };
}

export function parseCvHistoryPage(raw: unknown): CvHistoryPage {
  if (!isObject(raw)) {
    throw new Error('cv history page must be an object');
  }
  rejectForbiddenKeys(raw, 'cv history page');
  if (!Array.isArray(raw.items)) {
    throw new Error('cv history page.items must be an array');
  }
  return {
    items: raw.items.map(parseCvHistoryItem),
    next_cursor: optionalString(raw, 'next_cursor', 'cv history page'),
  };
}

export function parseChunkListItem(raw: unknown): ChunkListItem {
  if (!isObject(raw)) {
    throw new Error('chunk list item must be an object');
  }
  rejectForbiddenKeys(raw, 'chunk list item');
  if ('text' in raw) {
    throw new Error('chunk list item must not include full text');
  }
  const ordinal = requireNonNegInt(raw, 'ordinal', 'chunk list item');
  const char_count = asNumber(raw.char_count);
  if (char_count === null || !Number.isInteger(char_count) || char_count <= 0) {
    throw new Error('chunk list item.char_count must be a positive integer');
  }
  return {
    attachment_id: requireString(raw, 'attachment_id', 'chunk list item'),
    ordinal,
    preview: requireString(raw, 'preview', 'chunk list item'),
    char_count,
    token_estimate: requireNonNegInt(raw, 'token_estimate', 'chunk list item'),
    created_at: requireString(raw, 'created_at', 'chunk list item'),
  };
}

export function parseChunkListPage(raw: unknown): ChunkListPage {
  if (!isObject(raw)) {
    throw new Error('chunk list page must be an object');
  }
  rejectForbiddenKeys(raw, 'chunk list page');
  if (!Array.isArray(raw.items)) {
    throw new Error('chunk list page.items must be an array');
  }
  return {
    items: raw.items.map(parseChunkListItem),
    next_cursor: optionalString(raw, 'next_cursor', 'chunk list page'),
  };
}

export function parseChunkDetail(raw: unknown): ChunkDetail {
  if (!isObject(raw)) {
    throw new Error('chunk detail must be an object');
  }
  rejectForbiddenKeys(raw, 'chunk detail');
  const char_count = asNumber(raw.char_count);
  if (char_count === null || !Number.isInteger(char_count) || char_count <= 0) {
    throw new Error('chunk detail.char_count must be a positive integer');
  }
  return {
    attachment_id: requireString(raw, 'attachment_id', 'chunk detail'),
    ordinal: requireNonNegInt(raw, 'ordinal', 'chunk detail'),
    text: requireString(raw, 'text', 'chunk detail'),
    preview: requireString(raw, 'preview', 'chunk detail'),
    char_count,
    token_estimate: requireNonNegInt(raw, 'token_estimate', 'chunk detail'),
    created_at: requireString(raw, 'created_at', 'chunk detail'),
  };
}

function parseToolExecution(raw: unknown): ObservabilityToolExecution {
  if (!isObject(raw)) {
    throw new Error('tool execution must be an object');
  }
  rejectForbiddenKeys(raw, 'tool execution');
  const status = asString(raw.status);
  if (!status || !(TOOL_STATUSES as readonly string[]).includes(status)) {
    throw new Error('tool execution.status is invalid');
  }
  const durationRaw = raw.duration_ms;
  let duration_ms: number | null = null;
  if (durationRaw !== null && durationRaw !== undefined) {
    duration_ms = asNumber(durationRaw);
    if (
      duration_ms === null ||
      !Number.isInteger(duration_ms) ||
      duration_ms < 0
    ) {
      throw new Error('tool execution.duration_ms must be non-negative int or null');
    }
  }
  return {
    id: requireString(raw, 'id', 'tool execution'),
    tool_name: requireString(raw, 'tool_name', 'tool execution'),
    status: status as ToolStatus,
    duration_ms,
    error_code: optionalString(raw, 'error_code', 'tool execution'),
    summary: optionalString(raw, 'summary', 'tool execution'),
  };
}

export function parseRunHistoryItem(raw: unknown): RunHistoryItem {
  if (!isObject(raw)) {
    throw new Error('run history item must be an object');
  }
  rejectForbiddenKeys(raw, 'run history item');
  const state = asString(raw.state);
  if (!state || !(RUN_STATES as readonly string[]).includes(state)) {
    throw new Error('run history item.state is invalid');
  }
  if (!Array.isArray(raw.tool_executions)) {
    throw new Error('run history item.tool_executions must be an array');
  }
  return {
    id: requireString(raw, 'id', 'run history item'),
    user_message_id: requireString(raw, 'user_message_id', 'run history item'),
    state: state as RunState,
    error_code: optionalString(raw, 'error_code', 'run history item'),
    completed_at: optionalString(raw, 'completed_at', 'run history item'),
    created_at: requireString(raw, 'created_at', 'run history item'),
    updated_at: requireString(raw, 'updated_at', 'run history item'),
    related_attachment_ids: parseStringList(
      raw.related_attachment_ids,
      'run history item.related_attachment_ids',
    ),
    related_job_ids: parseStringList(
      raw.related_job_ids,
      'run history item.related_job_ids',
    ),
    tool_executions: raw.tool_executions.map(parseToolExecution),
  };
}

export function parseRunHistoryPage(raw: unknown): RunHistoryPage {
  if (!isObject(raw)) {
    throw new Error('run history page must be an object');
  }
  rejectForbiddenKeys(raw, 'run history page');
  if (!Array.isArray(raw.items)) {
    throw new Error('run history page.items must be an array');
  }
  return {
    items: raw.items.map(parseRunHistoryItem),
    next_cursor: optionalString(raw, 'next_cursor', 'run history page'),
  };
}

export function parseGraphSnapshot(raw: unknown): GraphSnapshot {
  if (!isObject(raw)) {
    throw new Error('graph snapshot must be an object');
  }
  rejectForbiddenKeys(raw, 'graph snapshot');
  const status = asString(raw.status);
  if (!status || !GRAPH_STATUSES.has(status)) {
    throw new Error('graph snapshot.status is invalid');
  }
  const summary = requireString(raw, 'summary', 'graph snapshot');
  let candidate: GraphCandidateNode | null = null;
  if (raw.candidate !== null && raw.candidate !== undefined) {
    if (!isObject(raw.candidate)) {
      throw new Error('graph snapshot.candidate must be object or null');
    }
    rejectForbiddenKeys(raw.candidate, 'graph candidate');
    candidate = {
      id: requireString(raw.candidate, 'id', 'graph candidate'),
      revision: requireString(raw.candidate, 'revision', 'graph candidate'),
    };
  }
  if (!Array.isArray(raw.jobs) || !Array.isArray(raw.skills) || !Array.isArray(raw.edges)) {
    throw new Error('graph snapshot jobs/skills/edges must be arrays');
  }
  const jobs = raw.jobs.map((item, index) => {
    if (!isObject(item)) {
      throw new Error(`graph job[${index}] must be an object`);
    }
    rejectForbiddenKeys(item, `graph job[${index}]`);
    return {
      id: requireString(item, 'id', `graph job[${index}]`),
      title: asString(item.title) ?? '',
      company: asString(item.company) ?? '',
      revision: requireString(item, 'revision', `graph job[${index}]`),
    };
  });
  const skills = raw.skills.map((item, index) => {
    if (!isObject(item)) {
      throw new Error(`graph skill[${index}] must be an object`);
    }
    rejectForbiddenKeys(item, `graph skill[${index}]`);
    return {
      canonical_name: requireString(
        item,
        'canonical_name',
        `graph skill[${index}]`,
      ),
    };
  });
  const edges = raw.edges.map((item, index) => {
    if (!isObject(item)) {
      throw new Error(`graph edge[${index}] must be an object`);
    }
    rejectForbiddenKeys(item, `graph edge[${index}]`);
    const type = asString(item.type);
    if (!type || !GRAPH_EDGE_TYPES.has(type)) {
      throw new Error(`graph edge[${index}].type is invalid`);
    }
    return {
      source_id: requireString(item, 'source_id', `graph edge[${index}]`),
      target_id: requireString(item, 'target_id', `graph edge[${index}]`),
      type: type as GraphEdgeType,
    };
  });
  const nodes_truncated = asBoolean(raw.nodes_truncated);
  const edges_truncated = asBoolean(raw.edges_truncated);
  if (nodes_truncated === null || edges_truncated === null) {
    throw new Error('graph truncation flags must be boolean');
  }
  return {
    status: status as GraphStatus,
    code: optionalString(raw, 'code', 'graph snapshot'),
    summary,
    rebuild_instruction: optionalString(
      raw,
      'rebuild_instruction',
      'graph snapshot',
    ),
    candidate,
    jobs,
    skills,
    edges,
    nodes_truncated,
    edges_truncated,
    omitted_node_count: requireNonNegInt(
      raw,
      'omitted_node_count',
      'graph snapshot',
    ),
    omitted_edge_count: requireNonNegInt(
      raw,
      'omitted_edge_count',
      'graph snapshot',
    ),
    checked_at: requireString(raw, 'checked_at', 'graph snapshot'),
  };
}

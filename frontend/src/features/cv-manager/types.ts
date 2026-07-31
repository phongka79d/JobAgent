export const CV_MANAGER_STATES = [
  'staged',
  'active',
  'archived',
  'failed',
  'deleting',
] as const;
export type CvManagerState = (typeof CV_MANAGER_STATES)[number];

export const CV_MANAGER_ACTIONS = [
  'preview',
  'download',
  'reextract',
  'activate_profile',
  'retry_upload',
  'delete_cv',
] as const;
export type CvManagerAction = (typeof CV_MANAGER_ACTIONS)[number];

export type CvManagerItem = {
  id: string;
  original_name: string;
  state: CvManagerState;
  failure_code: string | null;
  page_count: number | null;
  file_available: boolean;
  profile_id: string | null;
  profile_display_name: string | null;
  profile_state: 'pending' | 'ready' | 'deleting' | null;
  is_active_profile: boolean;
  allowed_actions: readonly CvManagerAction[];
  created_at: string;
  updated_at: string;
};

export type CvManagerListResponse = {items: CvManagerItem[]};

const ITEM_KEYS = [
  'id', 'original_name', 'state', 'failure_code', 'page_count',
  'file_available', 'profile_id', 'profile_display_name', 'profile_state',
  'is_active_profile', 'allowed_actions', 'created_at', 'updated_at',
] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function record(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, keys: readonly string[], name: string): void {
  const expected = new Set(keys);
  if (Object.keys(value).some((key) => !expected.has(key)) || keys.some((key) => !(key in value))) {
    throw new Error(`${name} has unexpected or missing fields`);
  }
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${name} must be a non-empty string`);
  return value;
}

function nullableString(value: unknown, name: string): string | null {
  return value === null ? null : requiredString(value, name);
}

function uuid(value: unknown, name: string): string {
  const result = requiredString(value, name);
  if (!UUID.test(result)) throw new Error(`${name} must be a UUID`);
  return result;
}

function timestamp(value: unknown, name: string): string {
  const result = requiredString(value, name);
  if (!ISO_TIMESTAMP.test(result) || Number.isNaN(Date.parse(result))) {
    throw new Error(`${name} must be an ISO timestamp with timezone`);
  }
  return result;
}

export function parseCvManagerItem(raw: unknown): CvManagerItem {
  const value = record(raw, 'CV manager item');
  exact(value, ITEM_KEYS, 'CV manager item');
  const state = value.state;
  if (!CV_MANAGER_STATES.includes(state as CvManagerState)) throw new Error('invalid CV state');
  if (typeof value.file_available !== 'boolean' || typeof value.is_active_profile !== 'boolean') {
    throw new Error('CV booleans are invalid');
  }
  const failure_code = nullableString(value.failure_code, 'failure_code');
  const page_count = value.page_count;
  if (page_count !== null && (!Number.isInteger(page_count) || (page_count as number) <= 0)) {
    throw new Error('page_count must be a positive integer or null');
  }
  const profile_id = value.profile_id === null ? null : uuid(value.profile_id, 'profile_id');
  const profile_display_name = nullableString(value.profile_display_name, 'profile_display_name');
  const profile_state = value.profile_state;
  if (profile_state !== null && !['pending', 'ready', 'deleting'].includes(profile_state as string)) {
    throw new Error('invalid profile_state');
  }
  if ((profile_id === null) !== (profile_display_name === null) || (profile_id === null) !== (profile_state === null)) {
    throw new Error('profile projection fields must be consistently nullable');
  }
  if (value.is_active_profile && (profile_id === null || profile_state !== 'ready')) {
    throw new Error('active profile projection is invalid');
  }
  if (!Array.isArray(value.allowed_actions)) throw new Error('allowed_actions must be an array');
  const allowed_actions = value.allowed_actions.map((action) => {
    if (!CV_MANAGER_ACTIONS.includes(action as CvManagerAction)) throw new Error('invalid allowed action');
    return action as CvManagerAction;
  });
  if (new Set(allowed_actions).size !== allowed_actions.length) throw new Error('allowed_actions must not contain duplicates');
  return {
    id: uuid(value.id, 'id'), original_name: requiredString(value.original_name, 'original_name'),
    state: state as CvManagerState, failure_code, page_count: page_count as number | null,
    file_available: value.file_available, profile_id, profile_display_name,
    profile_state: profile_state as CvManagerItem['profile_state'],
    is_active_profile: value.is_active_profile, allowed_actions,
    created_at: timestamp(value.created_at, 'created_at'), updated_at: timestamp(value.updated_at, 'updated_at'),
  };
}

export function parseCvManagerListResponse(raw: unknown): CvManagerListResponse {
  const value = record(raw, 'CV manager response');
  exact(value, ['items'], 'CV manager response');
  if (!Array.isArray(value.items)) throw new Error('items must be an array');
  return {items: value.items.map(parseCvManagerItem)};
}

export type ProfileReextractStage =
  | 'validating_source'
  | 'extracting_document'
  | 'projecting_profile'
  | 'publishing_review';

export type ProfileReextractEvent = {
  event_id: string;
  operation_id: string;
  profile_id: string;
  timestamp: string;
} & (
  | {event: 'reextract_progress'; payload: {stage: ProfileReextractStage; message: string}}
  | {event: 'reextract_review_ready'; payload: {revision: string}}
  | {event: 'reextract_failed'; payload: {code: string; summary: string; draft_available: boolean}}
);

export type PublicProfileSnapshot = {
  full_name: string | null;
  location: string | null;
  phone: string | null;
  email: string | null;
  github_url: string | null;
  summary: string;
  current_title: string | null;
  skill_labels: string[];
};

export type ProfileFieldChange = {
  field: 'full_name' | 'location' | 'phone' | 'email' | 'github_url' | 'summary' | 'current_title';
  before: string | number | null;
  after: string | number | null;
};

export type ProfilePreferenceChange = {
  field: 'target_roles' | 'preferred_locations' | 'acceptable_work_modes' | 'target_seniority';
  before: string[];
  after: string[];
};

export type ProfileReextractReview = {
  profile_id: string;
  /** Present on parsed server reviews; optional only for legacy test fixtures. */
  source?: 'agent_update' | 'reextract';
  operation_id?: string | null;
  operation_state?: 'review_ready' | 'stale' | null;
  revision: string;
  current: PublicProfileSnapshot;
  proposed: PublicProfileSnapshot;
  changed_fields: ProfileFieldChange[];
  preference_changes: ProfilePreferenceChange[];
  skills_added: string[];
  skills_removed: string[];
  collection_deltas: {experiences: number; education: number; languages: number; certifications: number};
  extraction_confidence: {before: number; after: number} | null;
  can_approve: boolean;
  can_discard: boolean;
};

export type ProfileReextractApprovalResponse = {
  profile_id: string;
  approved: boolean;
  sync_ok: boolean;
  warning: {code: string; summary: string; guidance: string} | null;
};

export type ProfileReextractOperation = {
  profile_id: string;
  operation_id: string;
  state: 'running' | 'review_ready' | 'interrupted' | 'failed' | 'stale';
  error_code: string | null;
  error_summary: string | null;
  review_revision: string | null;
  can_review: boolean;
  can_retry: boolean;
  can_discard: boolean;
};

export type ProfileReextractOperationEnvelope = {
  operation: ProfileReextractOperation | null;
};

const EVENT_KEYS = ['event_id', 'operation_id', 'profile_id', 'timestamp', 'event', 'payload'] as const;
const REVIEW_KEYS = ['profile_id', 'source', 'operation_id', 'operation_state', 'revision', 'current', 'proposed', 'changed_fields', 'preference_changes', 'skills_added', 'skills_removed', 'collection_deltas', 'extraction_confidence', 'can_approve', 'can_discard'] as const;
const OPERATION_KEYS = ['profile_id', 'operation_id', 'state', 'error_code', 'error_summary', 'review_revision', 'can_review', 'can_retry', 'can_discard'] as const;
const SNAPSHOT_KEYS = ['full_name', 'location', 'phone', 'email', 'github_url', 'summary', 'current_title', 'skill_labels'] as const;

function stringList(value: unknown, name: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) throw new Error(`${name} must be a string array`);
  return value as string[];
}

function bool(value: unknown, name: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`${name} must be boolean`);
  return value;
}

function finite(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${name} must be a number`);
  return value;
}

function parseSnapshot(raw: unknown): PublicProfileSnapshot {
  const value = record(raw, 'profile snapshot');
  exact(value, SNAPSHOT_KEYS, 'profile snapshot');
  return {
    full_name: nullableString(value.full_name, 'full_name'),
    location: nullableString(value.location, 'location'),
    phone: nullableString(value.phone, 'phone'),
    email: nullableString(value.email, 'email'),
    github_url: nullableString(value.github_url, 'github_url'),
    summary: typeof value.summary === 'string' ? value.summary : (() => { throw new Error('summary must be a string'); })(),
    current_title: nullableString(value.current_title, 'current_title'),
    skill_labels: stringList(value.skill_labels, 'skill_labels'),
  };
}

export function parseProfileReextractEvent(raw: unknown): ProfileReextractEvent {
  const value = record(raw, 'profile re-extract event');
  exact(value, EVENT_KEYS, 'profile re-extract event');
  const common = {
    event_id: uuid(value.event_id, 'event_id'),
    operation_id: uuid(value.operation_id, 'operation_id'),
    profile_id: uuid(value.profile_id, 'profile_id'),
    timestamp: timestamp(value.timestamp, 'timestamp'),
  };
  const payload = record(value.payload, 'profile re-extract payload');
  if (value.event === 'reextract_progress') {
    exact(payload, ['stage', 'message'], 'profile re-extract progress');
    const stages: ProfileReextractStage[] = ['validating_source', 'extracting_document', 'projecting_profile', 'publishing_review'];
    if (!stages.includes(payload.stage as ProfileReextractStage)) throw new Error('invalid re-extract stage');
    return {...common, event: value.event, payload: {stage: payload.stage as ProfileReextractStage, message: requiredString(payload.message, 'message')}};
  }
  if (value.event === 'reextract_review_ready') {
    exact(payload, ['revision'], 'profile re-extract review-ready');
    return {...common, event: value.event, payload: {revision: timestamp(payload.revision, 'revision')}};
  }
  if (value.event === 'reextract_failed') {
    exact(payload, ['code', 'summary', 'draft_available'], 'profile re-extract failure');
    return {...common, event: value.event, payload: {code: requiredString(payload.code, 'code'), summary: requiredString(payload.summary, 'summary'), draft_available: bool(payload.draft_available, 'draft_available')}};
  }
  throw new Error('invalid profile re-extract event');
}

export function parseProfileReextractOperation(raw: unknown): ProfileReextractOperation {
  const value = record(raw, 'profile re-extract operation');
  exact(value, OPERATION_KEYS, 'profile re-extract operation');
  const state = value.state;
  if (!['running', 'review_ready', 'interrupted', 'failed', 'stale'].includes(state as string)) {
    throw new Error('invalid profile re-extract operation state');
  }
  const error_code = nullableString(value.error_code, 'error_code');
  const error_summary = nullableString(value.error_summary, 'error_summary');
  const review_revision = value.review_revision === null ? null : timestamp(value.review_revision, 'review_revision');
  const can_review = bool(value.can_review, 'can_review');
  const can_retry = bool(value.can_retry, 'can_retry');
  const can_discard = bool(value.can_discard, 'can_discard');
  if ((error_code === null) !== (error_summary === null)) throw new Error('operation error fields must be consistently nullable');
  if ((state === 'running' || state === 'review_ready') !== (error_code === null)) throw new Error('operation error does not match state');
  if (state === 'review_ready' && review_revision === null) throw new Error('review-ready operation requires a review revision');
  if (!['review_ready', 'stale'].includes(state as string) && review_revision !== null) throw new Error('operation state cannot own a review revision');
  const expectedActions = state === 'running' ? [false, false, false]
    : state === 'review_ready' ? [true, false, true]
      : state === 'interrupted' || state === 'failed' ? [false, true, false]
        : review_revision === null ? [false, true, false] : [true, false, true];
  if (can_review !== expectedActions[0] || can_retry !== expectedActions[1] || can_discard !== expectedActions[2]) {
    throw new Error('operation actions do not match state');
  }
  return {profile_id: uuid(value.profile_id, 'profile_id'), operation_id: uuid(value.operation_id, 'operation_id'), state: state as ProfileReextractOperation['state'], error_code, error_summary, review_revision, can_review, can_retry, can_discard};
}

export function parseProfileReextractOperationEnvelope(raw: unknown): ProfileReextractOperationEnvelope {
  const value = record(raw, 'profile re-extract operation response');
  exact(value, ['operation'], 'profile re-extract operation response');
  return {operation: value.operation === null ? null : parseProfileReextractOperation(value.operation)};
}

export function parseProfileReextractReview(raw: unknown): ProfileReextractReview {
  const value = record(raw, 'profile re-extract review');
  exact(value, REVIEW_KEYS, 'profile re-extract review');
  if (!Array.isArray(value.changed_fields)) throw new Error('changed_fields must be an array');
  const changed_fields = value.changed_fields.map((rawChange) => {
    const change = record(rawChange, 'profile field change');
    exact(change, ['field', 'before', 'after'], 'profile field change');
    const fields = ['full_name', 'location', 'phone', 'email', 'github_url', 'summary', 'current_title'] as const;
    if (!fields.includes(change.field as (typeof fields)[number])) throw new Error('invalid changed field');
    const validValue = (item: unknown) => item === null || typeof item === 'string' || typeof item === 'number';
    if (!validValue(change.before) || !validValue(change.after)) throw new Error('invalid field change value');
    return {field: change.field as ProfileFieldChange['field'], before: change.before as ProfileFieldChange['before'], after: change.after as ProfileFieldChange['after']};
  });
  if (!Array.isArray(value.preference_changes)) throw new Error('preference_changes must be an array');
  const preference_changes = value.preference_changes.map((rawChange) => {
    const change = record(rawChange, 'profile preference change');
    exact(change, ['field', 'before', 'after'], 'profile preference change');
    const fields = ['target_roles', 'preferred_locations', 'acceptable_work_modes', 'target_seniority'] as const;
    if (!fields.includes(change.field as (typeof fields)[number])) throw new Error('invalid preference change field');
    return {
      field: change.field as ProfilePreferenceChange['field'],
      before: stringList(change.before, 'preference change before'),
      after: stringList(change.after, 'preference change after'),
    };
  });
  const deltas = record(value.collection_deltas, 'collection deltas');
  exact(deltas, ['experiences', 'education', 'languages', 'certifications'], 'collection deltas');
  let extraction_confidence: ProfileReextractReview['extraction_confidence'] = null;
  if (value.extraction_confidence !== null) {
    const confidence = record(value.extraction_confidence, 'confidence delta');
    exact(confidence, ['before', 'after'], 'confidence delta');
    extraction_confidence = {before: finite(confidence.before, 'confidence before'), after: finite(confidence.after, 'confidence after')};
  }
  const source = value.source;
  if (source !== 'agent_update' && source !== 'reextract') throw new Error('invalid review source');
  const operation_id = value.operation_id === null ? null : uuid(value.operation_id, 'operation_id');
  const operation_state = value.operation_state;
  if (operation_state !== null && operation_state !== 'review_ready' && operation_state !== 'stale') throw new Error('invalid review operation state');
  const can_approve = bool(value.can_approve, 'can_approve');
  const can_discard = bool(value.can_discard, 'can_discard');
  if (source === 'agent_update' && (operation_id !== null || operation_state !== null || !can_approve || !can_discard)) throw new Error('ordinary review ownership is invalid');
  if (source === 'reextract' && (operation_id === null || operation_state === null || !can_discard || (operation_state === 'review_ready' && !can_approve) || (operation_state === 'stale' && can_approve))) {
    throw new Error('re-extract review ownership is invalid');
  }
  return {
    profile_id: uuid(value.profile_id, 'profile_id'), source, operation_id, operation_state, revision: timestamp(value.revision, 'revision'),
    current: parseSnapshot(value.current), proposed: parseSnapshot(value.proposed), changed_fields, preference_changes,
    skills_added: stringList(value.skills_added, 'skills_added'), skills_removed: stringList(value.skills_removed, 'skills_removed'),
    collection_deltas: {experiences: finite(deltas.experiences, 'experiences'), education: finite(deltas.education, 'education'), languages: finite(deltas.languages, 'languages'), certifications: finite(deltas.certifications, 'certifications')},
    extraction_confidence, can_approve, can_discard,
  };
}

export function parseProfileReextractApproval(raw: unknown): ProfileReextractApprovalResponse {
  const value = record(raw, 'profile re-extract approval');
  exact(value, ['profile_id', 'approved', 'sync_ok', 'warning'], 'profile re-extract approval');
  let warning: ProfileReextractApprovalResponse['warning'] = null;
  if (value.warning !== null) {
    const item = record(value.warning, 'approval warning');
    exact(item, ['code', 'summary', 'guidance'], 'approval warning');
    warning = {code: requiredString(item.code, 'warning code'), summary: requiredString(item.summary, 'warning summary'), guidance: requiredString(item.guidance, 'warning guidance')};
  }
  return {profile_id: uuid(value.profile_id, 'profile_id'), approved: bool(value.approved, 'approved'), sync_ok: bool(value.sync_ok, 'sync_ok'), warning};
}

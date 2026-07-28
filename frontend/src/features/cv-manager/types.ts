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

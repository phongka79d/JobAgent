import type {
  AttachmentPublic,
  AttachmentState,
  JobPreferencesSummary,
} from './types';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export type ProfileSkillTag = {key: string; label: string};
export type ProfileAttachmentState = AttachmentState;
export type ProfileSetupStatus =
  | 'awaiting_extraction'
  | 'awaiting_approval'
  | 'extraction_failed';
export type CandidateSkillDetail = {
  skill: {canonical_key: string; display_name: string; aliases: string[]; category: string | null};
  confidence: number;
  proficiency: 'beginner' | 'intermediate' | 'advanced' | 'unknown';
  years: number | null;
  source: 'cv' | 'user_correction';
  excluded: boolean;
  evidence: string[];
};
export type ExperienceDetail = {
  title: string; company: string | null; start_date_text: string | null; end_date_text: string | null; summary: string;
};
export type EducationDetail = {institution: string; degree: string | null; field: string | null; graduation_year: number | null};
export type LanguageDetail = {name: string; proficiency: string | null};
export type CandidateProfileDetail = {
  full_name: string | null; location: string | null; phone: string | null; email: string | null; github_url: string | null; summary: string; current_title: string | null;
  total_experience_years: number | null; skills: CandidateSkillDetail[]; experiences: ExperienceDetail[];
  education: EducationDetail[]; languages: LanguageDetail[]; extraction_confidence: number;
};
export type ProfileListItem = {
  id: string; display_name: string; cv_filename: string; attachment_state: ProfileAttachmentState;
  location: string | null; skill_tags: ProfileSkillTag[]; skill_count: number; extraction_version: string | null;
  source_hash: string | null; state: 'pending' | 'ready' | 'deleting'; setup_status: ProfileSetupStatus | null;
  is_active: boolean; created_at: string; updated_at: string; last_opened_at: string;
};
export type ProfileDetail = ProfileListItem & {
  profile: CandidateProfileDetail; preferences: JobPreferencesSummary; attachment: import('./types').AttachmentPublic;
  selected_conversation_id: string | null;
};
export type ConversationSummary = {
  id: string; profile_id: string; title: string; created_at: string; updated_at: string; last_opened_at: string; is_selected: boolean;
};
export type SafeWarning = {code: string; summary: string; guidance: string};
export type SelectionResponse = {profile: ProfileDetail; conversation: ConversationSummary | null; warning: SafeWarning | null};
export type ProfileListResponse = {items: ProfileListItem[]; active_profile_id: string | null};
export type ConversationListResponse = {items: ConversationSummary[]; next_cursor: string | null};
export type ConversationMutationResponse = {conversation: ConversationSummary};
export type ConversationDeleteResponse = {deleted_conversation_id: string; selected_conversation: ConversationSummary; replacement_conversation_id: string | null};
export type ProfileDeleteResponse = {deleted_profile_id: string; active_profile: ProfileListItem | null; selected_conversation: ConversationSummary | null};

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error('expected object');
  return value as Record<string, unknown>;
}
function exact(value: Record<string, unknown>, keys: readonly string[]): void {
  const expected = new Set(keys);
  if (Object.keys(value).some((key) => !expected.has(key)) || keys.some((key) => !(key in value))) throw new Error('unexpected response field');
}
function uuid(value: unknown): string {
  if (typeof value !== 'string' || !UUID_V4.test(value)) throw new Error('invalid UUID');
  return value;
}
function string(value: unknown, name: string): string { if (typeof value !== 'string') throw new Error(`${name} must be string`); return value; }
function nullableString(value: unknown, name: string): string | null { if (value === null) return null; return string(value, name); }

export function parseAttachmentPublic(raw: unknown): AttachmentPublic {
  const value = object(raw);
  if ('storage_path' in value) throw new Error('attachment must not include storage_path');
  exact(value, ['id','original_name','mime_type','size_bytes','page_count','state','failure_code']);
  if (value.mime_type !== 'application/pdf') throw new Error('invalid attachment mime_type');
  if (typeof value.size_bytes !== 'number' || !Number.isFinite(value.size_bytes) || value.size_bytes <= 0) throw new Error('attachment size_bytes must be positive');
  if (value.page_count !== null && (typeof value.page_count !== 'number' || !Number.isFinite(value.page_count) || value.page_count <= 0)) throw new Error('attachment page_count must be positive or null');
  if (!['staged','active','archived','failed','deleting'].includes(String(value.state))) throw new Error('invalid attachment state');
  return {
    id: uuid(value.id),
    original_name: string(value.original_name, 'original_name'),
    mime_type: 'application/pdf',
    size_bytes: value.size_bytes,
    page_count: value.page_count as number | null,
    state: value.state as AttachmentState,
    failure_code: nullableString(value.failure_code, 'failure_code'),
  };
}

export function parseConversationSummary(raw: unknown): ConversationSummary {
  const value = object(raw); exact(value, ['id', 'profile_id', 'title', 'created_at', 'updated_at', 'last_opened_at', 'is_selected']);
  if (typeof value.is_selected !== 'boolean') throw new Error('is_selected must be boolean');
  return {id: uuid(value.id), profile_id: uuid(value.profile_id), title: string(value.title, 'title'), created_at: string(value.created_at, 'created_at'), updated_at: string(value.updated_at, 'updated_at'), last_opened_at: string(value.last_opened_at, 'last_opened_at'), is_selected: value.is_selected};
}
export function parseProfileListItem(raw: unknown): ProfileListItem {
  const value = object(raw); exact(value, ['id','display_name','cv_filename','attachment_state','location','skill_tags','skill_count','extraction_version','source_hash','state','setup_status','is_active','created_at','updated_at','last_opened_at']);
  const tags = value.skill_tags; if (!Array.isArray(tags)) throw new Error('skill_tags must be array');
  if (!['staged','active','archived','failed','deleting'].includes(String(value.attachment_state))) throw new Error('invalid attachment_state');
  if (!['pending','ready','deleting'].includes(String(value.state))) throw new Error('invalid profile state');
  if (typeof value.is_active !== 'boolean') throw new Error('is_active must be boolean');
  if (typeof value.skill_count !== 'number' || !Number.isInteger(value.skill_count) || value.skill_count < 0) throw new Error('skill_count must be a non-negative integer');
  const location = nullableString(value.location,'location');
  const extraction_version = nullableString(value.extraction_version,'extraction_version');
  const source_hash = nullableString(value.source_hash,'source_hash');
  const setup_status = value.setup_status === null ? null : string(value.setup_status,'setup_status') as ProfileSetupStatus;
  if (setup_status !== null && !['awaiting_extraction','awaiting_approval','extraction_failed'].includes(setup_status)) throw new Error('invalid setup_status');
  const state = value.state as ProfileListItem['state'];
  const attachment_state = value.attachment_state as ProfileAttachmentState;
  if (state === 'pending' && (extraction_version !== null || source_hash !== null || location !== null || tags.length !== 0 || value.skill_count !== 0 || setup_status === null || !['staged','failed'].includes(attachment_state))) throw new Error('inconsistent pending profile');
  if (state === 'pending' && ((attachment_state === 'failed') !== (setup_status === 'extraction_failed'))) throw new Error('inconsistent pending failure status');
  if (state === 'ready' && (extraction_version === null || source_hash === null || setup_status !== null || !['active','archived'].includes(attachment_state))) throw new Error('inconsistent ready profile');
  if (state === 'deleting' && (setup_status !== null || attachment_state !== 'deleting')) throw new Error('inconsistent deleting profile');
  return {id: uuid(value.id), display_name: string(value.display_name,'display_name'), cv_filename: string(value.cv_filename,'cv_filename'), attachment_state, location, skill_tags: tags.map((tag) => { const item = object(tag); exact(item,['key','label']); return {key:string(item.key,'key'),label:string(item.label,'label')}; }), skill_count: value.skill_count, extraction_version, source_hash, state, setup_status, is_active: value.is_active, created_at: string(value.created_at,'created_at'), updated_at: string(value.updated_at,'updated_at'), last_opened_at: string(value.last_opened_at,'last_opened_at')};
}
export function parseProfileListResponse(raw: unknown): ProfileListResponse {
  const value = object(raw); exact(value, ['items','active_profile_id']); if (!Array.isArray(value.items)) throw new Error('items must be array');
  return {items: value.items.map(parseProfileListItem), active_profile_id: value.active_profile_id === null ? null : uuid(value.active_profile_id)};
}
export function parseConversationListResponse(raw: unknown): ConversationListResponse {
  const value = object(raw); exact(value, ['items','next_cursor']); if (!Array.isArray(value.items)) throw new Error('items must be array');
  return {items: value.items.map(parseConversationSummary), next_cursor: nullableString(value.next_cursor, 'next_cursor')};
}

export function parseConversationMutationResponse(raw: unknown): ConversationMutationResponse {
  const value = object(raw); exact(value, ['conversation']);
  return {conversation: parseConversationSummary(value.conversation)};
}

export function parseConversationDeleteResponse(raw: unknown): ConversationDeleteResponse {
  const value = object(raw); exact(value, ['deleted_conversation_id','selected_conversation','replacement_conversation_id']);
  return {deleted_conversation_id: uuid(value.deleted_conversation_id), selected_conversation: parseConversationSummary(value.selected_conversation), replacement_conversation_id: value.replacement_conversation_id === null ? null : uuid(value.replacement_conversation_id)};
}

export function parseProfileDetail(raw: unknown): ProfileDetail {
  const value = object(raw);
  exact(value, ['id','display_name','cv_filename','attachment_state','location','skill_tags','skill_count','extraction_version','source_hash','state','setup_status','is_active','created_at','updated_at','last_opened_at','profile','preferences','attachment','selected_conversation_id']);
  const listKeys = ['id','display_name','cv_filename','attachment_state','location','skill_tags','skill_count','extraction_version','source_hash','state','setup_status','is_active','created_at','updated_at','last_opened_at'] as const;
  const listRaw = Object.fromEntries(listKeys.map((key) => [key, value[key]]));
  const profile = object(value.profile);
  exact(profile, ['full_name','location','phone','email','github_url','summary','current_title','total_experience_years','skills','experiences','education','languages','extraction_confidence']);
  const preferences = object(value.preferences);
  exact(preferences, ['target_roles','preferred_locations','acceptable_work_modes','target_seniority']);
  const stringList = (item: unknown, name: string): string[] => { if (!Array.isArray(item) || item.some((entry) => typeof entry !== 'string')) throw new Error(`${name} must be string array`); return item as string[]; };
  return {...parseProfileListItem(listRaw), profile: profile as CandidateProfileDetail, preferences: {target_roles:stringList(preferences.target_roles,'target_roles'), preferred_locations:stringList(preferences.preferred_locations,'preferred_locations'), acceptable_work_modes:stringList(preferences.acceptable_work_modes,'acceptable_work_modes'), target_seniority:stringList(preferences.target_seniority,'target_seniority')}, attachment: parseAttachmentPublic(value.attachment), selected_conversation_id: value.selected_conversation_id === null ? null : uuid(value.selected_conversation_id)};
}

export function parseSelectionResponse(raw: unknown): SelectionResponse {
  const value = object(raw); exact(value, ['profile','conversation','warning']);
  let warning: SafeWarning | null = null;
  if (value.warning !== null) { const item = object(value.warning); exact(item,['code','summary','guidance']); warning = {code:string(item.code,'code'),summary:string(item.summary,'summary'),guidance:string(item.guidance,'guidance')}; }
  return {profile: parseProfileDetail(value.profile), conversation: value.conversation === null ? null : parseConversationSummary(value.conversation), warning};
}

export function parseProfileDeleteResponse(raw: unknown): ProfileDeleteResponse {
  const value = object(raw); exact(value, ['deleted_profile_id','active_profile','selected_conversation']);
  return {deleted_profile_id: uuid(value.deleted_profile_id), active_profile: value.active_profile === null ? null : parseProfileListItem(value.active_profile), selected_conversation: value.selected_conversation === null ? null : parseConversationSummary(value.selected_conversation)};
}

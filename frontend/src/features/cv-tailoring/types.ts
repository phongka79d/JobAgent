import {
  isUuidV4,
  parseSseEventData,
  SseParseError,
  type JsonObject,
  type SseEvent,
} from '../chat/types';
import type {SseWireFrame} from '../../lib/sse/parser';
import type {TypedSseParseResult} from '../../lib/sse/stream';

export const CREATE_TAILORED_CV_TOOL_NAME = 'create_tailored_cv' as const;

export type CreateTailoredCvResultData = {
  readonly outcome: 'version_created';
  readonly session_id: string;
  readonly version_id: string;
  readonly status: 'ready';
  readonly currentness: 'current';
};

export const CV_TAILORING_SESSION_HEADER =
  'X-CV-Tailoring-Session-Id' as const;

export type TailoringErrorCode =
  | 'PROFILE_NOT_READY'
  | 'TAILORING_CONTACT_REQUIRED'
  | 'JOB_NOT_SCORABLE'
  | 'TAILORING_SESSION_NOT_FOUND'
  | 'TAILORING_VERSION_NOT_FOUND'
  | 'TAILORING_SOURCE_STALE'
  | 'TAILORING_PARENT_CONFLICT'
  | 'TAILORING_GROUNDING_FAILED'
  | 'TAILORING_COMPILE_FAILED'
  | 'TAILORING_ARTIFACT_UNAVAILABLE'
  | 'TAILORING_DELETE_FAILED';

export const TAILORING_ERROR_CODES: readonly TailoringErrorCode[] = [
  'PROFILE_NOT_READY',
  'TAILORING_CONTACT_REQUIRED',
  'JOB_NOT_SCORABLE',
  'TAILORING_SESSION_NOT_FOUND',
  'TAILORING_VERSION_NOT_FOUND',
  'TAILORING_SOURCE_STALE',
  'TAILORING_PARENT_CONFLICT',
  'TAILORING_GROUNDING_FAILED',
  'TAILORING_COMPILE_FAILED',
  'TAILORING_ARTIFACT_UNAVAILABLE',
  'TAILORING_DELETE_FAILED',
] as const;

export type CvSectionKind =
  | 'summary'
  | 'experience'
  | 'education'
  | 'skills'
  | 'languages'
  | 'certifications'
  | 'projects'
  | 'awards'
  | 'publications'
  | 'volunteering'
  | 'interests'
  | 'references'
  | 'other';

const SECTION_KINDS: readonly CvSectionKind[] = [
  'summary',
  'experience',
  'education',
  'skills',
  'languages',
  'certifications',
  'projects',
  'awards',
  'publications',
  'volunteering',
  'interests',
  'references',
  'other',
] as const;

export type SourceBoundText = {
  readonly text: string;
  readonly source_fact_ids: readonly string[];
};

export type TailoredAttribute = {
  readonly name: string;
  readonly values: readonly SourceBoundText[];
};

export type TailoredItem = {
  readonly id: string;
  readonly source_entry_id: string | null;
  readonly title: SourceBoundText | null;
  readonly subtitle: SourceBoundText | null;
  readonly date_text: SourceBoundText | null;
  readonly location: SourceBoundText | null;
  readonly body: SourceBoundText;
  readonly bullets: readonly SourceBoundText[];
  readonly attributes: readonly TailoredAttribute[];
};

export type TailoredSection = {
  readonly id: string;
  readonly ordinal: number;
  readonly heading: string;
  readonly kind: CvSectionKind;
  readonly items: readonly TailoredItem[];
};

export type TailoredHeaderSnapshot = {
  readonly full_name: string;
  readonly location: string | null;
  readonly phone: string | null;
  readonly email: string | null;
  readonly github_url: string | null;
};

export type TailoredCVContent = {
  readonly header: TailoredHeaderSnapshot;
  readonly sections: readonly TailoredSection[];
};

export type TailoredFactEvidence = {
  readonly fact_id: string;
  readonly section_id: string;
  readonly source_entry_id: string;
  readonly field_path: string;
  readonly source_text: string;
};

export type TailoringJobLabel = {
  readonly title: string | null;
  readonly company: string | null;
  readonly display_label: string | null;
};

export type TailoringVersionSummary = {
  readonly id: string;
  readonly version_number: number;
  readonly parent_version_id: string | null;
  readonly created_by: 'ai' | 'user';
  readonly page_count: number;
  readonly page_warning: string | null;
  readonly created_at: string;
};

export type TailoringSessionSummary = {
  readonly id: string;
  readonly profile_id: string;
  readonly job_label: TailoringJobLabel | null;
  readonly instruction: string;
  readonly template_version: 'latex-cv-v1';
  readonly state: 'generating' | 'ready' | 'failed' | 'deleting';
  readonly currentness: 'current' | 'stale';
  readonly latest_version_number: number;
  readonly error_code: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type TailoringSessionListResponse = {
  readonly items: readonly TailoringSessionSummary[];
};

export type TailoringActivity = {
  readonly activity_id: string;
  readonly run_id: string;
  readonly sequence: number;
  readonly kind: 'assistant' | 'tool';
  readonly label: string;
  readonly technical_name: string | null;
  readonly state: 'pending' | 'running' | 'completed' | 'failed';
  readonly started_at: string;
  readonly updated_at: string;
  readonly completed_at: string | null;
  readonly duration_ms: number | null;
  readonly error_code: string | null;
};

export type TailoringRunSummary = {
  readonly id: string;
  readonly state: 'running' | 'interrupted' | 'completed' | 'failed';
  readonly error_code: string | null;
  readonly activities: readonly TailoringActivity[];
  readonly issues: readonly TailoringUserIssue[];
};

export type TailoringUserIssue = {
  readonly section_id: string;
  readonly section_heading: string;
  readonly item_index: number | null;
  readonly field: 'title' | 'subtitle' | 'date' | 'location' | 'body' | 'bullet' | 'attribute' | 'section';
  readonly reason: 'not_in_source' | 'belongs_to_another_section' | 'structure_changed' | 'required_source_missing' | 'unsupported_value';
};

function safeIssueToken(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]/g, '-');
}

export function tailoringIssueId(issue: TailoringUserIssue): string {
  return `tailoring-issue-${safeIssueToken(issue.section_id)}-${issue.item_index ?? 'section'}-${issue.field}-${issue.reason}`;
}

export function tailoringSectionId(sectionId: string): string {
  return `tailoring-section-${safeIssueToken(sectionId)}`;
}

export function tailoringFieldId(
  sectionId: string,
  itemIndex: number,
  field: TailoringUserIssue['field'],
): string {
  return `tailoring-field-${safeIssueToken(sectionId)}-${itemIndex}-${field}`;
}

export type TailoringSessionDetailResponse = {
  readonly session: TailoringSessionSummary;
  readonly versions: readonly TailoringVersionSummary[];
  readonly selected_version: TailoringVersionSummary | null;
  readonly content: TailoredCVContent | null;
  readonly evidence: readonly TailoredFactEvidence[];
  readonly latest_run: TailoringRunSummary | null;
  readonly source_available: boolean;
  readonly pdf_available: boolean;
};

export type TailoringMutationOutcome = 'version_created' | 'no_change';

export type TailoringVersionMutationResponse = {
  readonly outcome: TailoringMutationOutcome;
  readonly session_id: string;
  readonly version_id: string;
  readonly version_number: number;
  readonly currentness: 'current';
};

export type TailoringSseEvent = Exclude<SseEvent, {event: 'run_completed' | 'run_failed'}> | {
  readonly event_id: string;
  readonly run_id: string;
  readonly timestamp: string;
  readonly event: 'run_completed';
  readonly payload: {
    readonly state: 'completed';
    readonly outcome?: TailoringMutationOutcome;
    readonly version_id?: string;
    readonly version_number?: number;
  };
} | {
  readonly event_id: string;
  readonly run_id: string;
  readonly timestamp: string;
  readonly event: 'run_failed';
  readonly payload: {
    readonly state: 'failed';
    readonly error_code: string;
    readonly summary: string;
    readonly issues?: readonly TailoringUserIssue[];
  };
};

export type TailoringDeleteResponse = {
  readonly deleted_session_id: string;
};

export type CreateTailoringSessionRequest = {
  readonly job_id: string | null;
  readonly instruction: string;
};

export type CreateTailoringAiVersionRequest = {
  readonly parent_version_id: string | null;
  readonly instruction: string;
  readonly target_section_ids: readonly string[];
};

export type CreateTailoringManualVersionRequest = {
  readonly parent_version_id: string;
  readonly content: TailoredCVContent;
};

const LATEX_SENTINELS = [
  '\\documentclass',
  '\\begin{document}',
  '\\usepackage',
] as const;

function object(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function exact(
  value: Record<string, unknown>,
  keys: readonly string[],
  path: string,
): void {
  const expected = new Set(keys);
  if (
    Object.keys(value).some((key) => !expected.has(key)) ||
    keys.some((key) => !Object.prototype.hasOwnProperty.call(value, key))
  ) {
    throw new Error(`${path} has unexpected or missing fields`);
  }
}

function text(
  value: unknown,
  path: string,
  max: number,
  allowEmpty = false,
): string {
  if (
    typeof value !== 'string' ||
    value.length > max ||
    (!allowEmpty && value.trim() === '')
  ) {
    throw new Error(`${path} must be a bounded string`);
  }
  const lower = value.toLowerCase();
  if (LATEX_SENTINELS.some((sentinel) => lower.includes(sentinel))) {
    throw new Error(`${path} must not contain LaTeX source`);
  }
  return value;
}

function nullableText(value: unknown, path: string, max: number): string | null {
  return value === null ? null : text(value, path, max);
}

function uuid(value: unknown, path: string): string {
  if (typeof value !== 'string' || !isUuidV4(value)) {
    throw new Error(`${path} must be a UUID v4`);
  }
  return value.toLowerCase();
}

function nullableUuid(value: unknown, path: string): string | null {
  return value === null ? null : uuid(value, path);
}

function integer(value: unknown, path: string, min = 0): number {
  if (!Number.isFinite(value) || !Number.isInteger(value) || Number(value) < min) {
    throw new Error(`${path} must be an integer >= ${min}`);
  }
  return Number(value);
}

const UTC_TIMESTAMP =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/;

function timestamp(value: unknown, path: string): string {
  if (
    typeof value !== 'string' ||
    !UTC_TIMESTAMP.test(value) ||
    Number.isNaN(Date.parse(value))
  ) {
    throw new Error(`${path} must be an aware UTC timestamp`);
  }
  return value;
}

function bool(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`${path} must be boolean`);
  return value;
}

function array(value: unknown, path: string, max: number): readonly unknown[] {
  if (!Array.isArray(value) || value.length > max) {
    throw new Error(`${path} must be a bounded array`);
  }
  return value;
}

function parseSourceText(raw: unknown, path: string): SourceBoundText {
  const value = object(raw, path);
  exact(value, ['text', 'source_fact_ids'], path);
  const factIds = array(value.source_fact_ids, `${path}.source_fact_ids`, 64).map(
    (item, index) => text(item, `${path}.source_fact_ids[${index}]`, 200),
  );
  if (new Set(factIds).size !== factIds.length) {
    throw new Error(`${path}.source_fact_ids must be unique`);
  }
  return {text: text(value.text, `${path}.text`, 4_000, true), source_fact_ids: factIds};
}

function nullableSourceText(raw: unknown, path: string): SourceBoundText | null {
  return raw === null ? null : parseSourceText(raw, path);
}

function parseAttribute(raw: unknown, path: string): TailoredAttribute {
  const value = object(raw, path);
  exact(value, ['name', 'values'], path);
  const values = array(value.values, `${path}.values`, 30);
  if (values.length === 0) throw new Error(`${path}.values must not be empty`);
  return {
    name: text(value.name, `${path}.name`, 120),
    values: values.map((item, index) =>
      parseSourceText(item, `${path}.values[${index}]`),
    ),
  };
}

function parseItem(raw: unknown, path: string): TailoredItem {
  const value = object(raw, path);
  exact(
    value,
    [
      'id',
      'source_entry_id',
      'title',
      'subtitle',
      'date_text',
      'location',
      'body',
      'bullets',
      'attributes',
    ],
    path,
  );
  return {
    id: text(value.id, `${path}.id`, 200),
    source_entry_id: nullableText(value.source_entry_id, `${path}.source_entry_id`, 200),
    title: nullableSourceText(value.title, `${path}.title`),
    subtitle: nullableSourceText(value.subtitle, `${path}.subtitle`),
    date_text: nullableSourceText(value.date_text, `${path}.date_text`),
    location: nullableSourceText(value.location, `${path}.location`),
    body: parseSourceText(value.body, `${path}.body`),
    bullets: array(value.bullets, `${path}.bullets`, 30).map((item, index) =>
      parseSourceText(item, `${path}.bullets[${index}]`),
    ),
    attributes: array(value.attributes, `${path}.attributes`, 30).map(
      (item, index) => parseAttribute(item, `${path}.attributes[${index}]`),
    ),
  };
}

function parseSection(raw: unknown, path: string): TailoredSection {
  const value = object(raw, path);
  exact(value, ['id', 'ordinal', 'heading', 'kind', 'items'], path);
  if (!SECTION_KINDS.includes(value.kind as CvSectionKind)) {
    throw new Error(`${path}.kind is invalid`);
  }
  return {
    id: text(value.id, `${path}.id`, 200),
    ordinal: integer(value.ordinal, `${path}.ordinal`),
    heading: text(value.heading, `${path}.heading`, 200),
    kind: value.kind as CvSectionKind,
    items: array(value.items, `${path}.items`, 30).map((item, index) =>
      parseItem(item, `${path}.items[${index}]`),
    ),
  };
}

export function parseTailoredContent(raw: unknown): TailoredCVContent {
  const value = object(raw, 'content');
  exact(value, ['header', 'sections'], 'content');
  const header = object(value.header, 'content.header');
  exact(
    header,
    ['full_name', 'location', 'phone', 'email', 'github_url'],
    'content.header',
  );
  const sectionsRaw = array(value.sections, 'content.sections', 20);
  if (sectionsRaw.length === 0) throw new Error('content.sections is required');
  const sections = sectionsRaw.map((item, index) =>
    parseSection(item, `content.sections[${index}]`),
  );
  if (sections.some((section, index) => section.ordinal !== index)) {
    throw new Error('content.sections ordinals must be contiguous');
  }
  if (new Set(sections.map((section) => section.id)).size !== sections.length) {
    throw new Error('content.sections ids must be unique');
  }
  return {
    header: {
      full_name: text(header.full_name, 'content.header.full_name', 200),
      location: nullableText(header.location, 'content.header.location', 200),
      phone: nullableText(header.phone, 'content.header.phone', 50),
      email: nullableText(header.email, 'content.header.email', 254),
      github_url: nullableText(header.github_url, 'content.header.github_url', 500),
    },
    sections,
  };
}

function parseJobLabel(raw: unknown, path: string): TailoringJobLabel | null {
  if (raw === null) return null;
  const value = object(raw, path);
  if (
    Object.keys(value).some((key) => !['title', 'company', 'display_label'].includes(key)) ||
    !Object.prototype.hasOwnProperty.call(value, 'title') ||
    !Object.prototype.hasOwnProperty.call(value, 'company')
  ) {
    throw new Error(`${path} has unexpected or missing fields`);
  }
  return {
    title: nullableText(value.title, `${path}.title`, 300),
    company: nullableText(value.company, `${path}.company`, 300),
    display_label:
      value.display_label === undefined
        ? null
        : nullableText(value.display_label, `${path}.display_label`, 140),
  };
}

function parseVersion(raw: unknown, path: string): TailoringVersionSummary {
  const value = object(raw, path);
  exact(
    value,
    [
      'id',
      'version_number',
      'parent_version_id',
      'created_by',
      'page_count',
      'page_warning',
      'created_at',
    ],
    path,
  );
  if (value.created_by !== 'ai' && value.created_by !== 'user') {
    throw new Error(`${path}.created_by is invalid`);
  }
  return {
    id: uuid(value.id, `${path}.id`),
    version_number: integer(value.version_number, `${path}.version_number`, 1),
    parent_version_id: nullableUuid(value.parent_version_id, `${path}.parent_version_id`),
    created_by: value.created_by,
    page_count: integer(value.page_count, `${path}.page_count`, 1),
    page_warning: nullableText(value.page_warning, `${path}.page_warning`, 4_000),
    created_at: timestamp(value.created_at, `${path}.created_at`),
  };
}

function parseSession(raw: unknown, path: string): TailoringSessionSummary {
  const value = object(raw, path);
  exact(
    value,
    [
      'id',
      'profile_id',
      'job_label',
      'instruction',
      'template_version',
      'state',
      'currentness',
      'latest_version_number',
      'error_code',
      'created_at',
      'updated_at',
    ],
    path,
  );
  if (value.template_version !== 'latex-cv-v1') {
    throw new Error(`${path}.template_version is invalid`);
  }
  if (!['generating', 'ready', 'failed', 'deleting'].includes(String(value.state))) {
    throw new Error(`${path}.state is invalid`);
  }
  if (value.currentness !== 'current' && value.currentness !== 'stale') {
    throw new Error(`${path}.currentness is invalid`);
  }
  return {
    id: uuid(value.id, `${path}.id`),
    profile_id: uuid(value.profile_id, `${path}.profile_id`),
    job_label: parseJobLabel(value.job_label, `${path}.job_label`),
    instruction: text(value.instruction, `${path}.instruction`, 4_000, true),
    template_version: 'latex-cv-v1',
    state: value.state as TailoringSessionSummary['state'],
    currentness: value.currentness,
    latest_version_number: integer(
      value.latest_version_number,
      `${path}.latest_version_number`,
    ),
    error_code: nullableText(value.error_code, `${path}.error_code`, 120),
    created_at: timestamp(value.created_at, `${path}.created_at`),
    updated_at: timestamp(value.updated_at, `${path}.updated_at`),
  };
}

function parseEvidence(raw: unknown, path: string): TailoredFactEvidence {
  const value = object(raw, path);
  exact(
    value,
    ['fact_id', 'section_id', 'source_entry_id', 'field_path', 'source_text'],
    path,
  );
  return {
    fact_id: text(value.fact_id, `${path}.fact_id`, 35),
    section_id: text(value.section_id, `${path}.section_id`, 200),
    source_entry_id: text(value.source_entry_id, `${path}.source_entry_id`, 200),
    field_path: text(value.field_path, `${path}.field_path`, 200),
    source_text: text(value.source_text, `${path}.source_text`, 4_000, true),
  };
}

function parseActivity(raw: unknown, runId: string, path: string): TailoringActivity {
  const value = object(raw, path);
  exact(
    value,
    [
      'activity_id',
      'run_id',
      'sequence',
      'kind',
      'label',
      'technical_name',
      'state',
      'started_at',
      'updated_at',
      'completed_at',
      'duration_ms',
      'error_code',
    ],
    path,
  );
  const activityRunId = uuid(value.run_id, `${path}.run_id`);
  if (activityRunId !== runId) throw new Error(`${path}.run_id mismatch`);
  if (value.kind !== 'assistant' && value.kind !== 'tool') {
    throw new Error(`${path}.kind is invalid`);
  }
  if (!['pending', 'running', 'completed', 'failed'].includes(String(value.state))) {
    throw new Error(`${path}.state is invalid`);
  }
  const completedAt =
    value.completed_at === null
      ? null
      : timestamp(value.completed_at, `${path}.completed_at`);
  const duration =
    value.duration_ms === null
      ? null
      : integer(value.duration_ms, `${path}.duration_ms`);
  const errorCode = nullableText(value.error_code, `${path}.error_code`, 120);
  const terminal = value.state === 'completed' || value.state === 'failed';
  if (terminal !== (completedAt !== null)) throw new Error(`${path} terminal mismatch`);
  if (!terminal && duration !== null) throw new Error(`${path} duration mismatch`);
  if ((value.state === 'failed') !== (errorCode !== null)) {
    throw new Error(`${path} error code mismatch`);
  }
  return {
    activity_id: uuid(value.activity_id, `${path}.activity_id`),
    run_id: activityRunId,
    sequence: integer(value.sequence, `${path}.sequence`),
    kind: value.kind,
    label: text(value.label, `${path}.label`, 160),
    technical_name: nullableText(value.technical_name, `${path}.technical_name`, 120),
    state: value.state as TailoringActivity['state'],
    started_at: timestamp(value.started_at, `${path}.started_at`),
    updated_at: timestamp(value.updated_at, `${path}.updated_at`),
    completed_at: completedAt,
    duration_ms: duration,
    error_code: errorCode,
  };
}

function parseRun(raw: unknown, path: string): TailoringRunSummary | null {
  if (raw === null) return null;
  const value = object(raw, path);
  exact(value, ['id', 'state', 'error_code', 'activities', 'issues'], path);
  if (!['running', 'interrupted', 'completed', 'failed'].includes(String(value.state))) {
    throw new Error(`${path}.state is invalid`);
  }
  const id = uuid(value.id, `${path}.id`);
  return {
    id,
    state: value.state as TailoringRunSummary['state'],
    error_code: nullableText(value.error_code, `${path}.error_code`, 120),
    activities: array(value.activities, `${path}.activities`, 20_000).map(
      (item, index) => parseActivity(item, id, `${path}.activities[${index}]`),
    ),
    issues: parseTailoringIssues(value.issues, `${path}.issues`),
  };
}

export function parseTailoringIssues(raw: unknown, path = 'issues'): TailoringUserIssue[] {
  return array(raw, path, 10).map((item, index) => {
    const value = object(item, `${path}[${index}]`);
    exact(value, ['section_id', 'section_heading', 'item_index', 'field', 'reason'], `${path}[${index}]`);
    const fields = ['title', 'subtitle', 'date', 'location', 'body', 'bullet', 'attribute', 'section'] as const;
    const reasons = ['not_in_source', 'belongs_to_another_section', 'structure_changed', 'required_source_missing', 'unsupported_value'] as const;
    if (!fields.includes(value.field as (typeof fields)[number])) throw new Error(`${path}[${index}].field is invalid`);
    if (!reasons.includes(value.reason as (typeof reasons)[number])) throw new Error(`${path}[${index}].reason is invalid`);
    const itemIndex = value.item_index === null ? null : integer(value.item_index, `${path}[${index}].item_index`);
    if (itemIndex !== null && itemIndex > 30) throw new Error(`${path}[${index}].item_index is invalid`);
    return {
      section_id: text(value.section_id, `${path}[${index}].section_id`, 120),
      section_heading: text(value.section_heading, `${path}[${index}].section_heading`, 200),
      item_index: itemIndex,
      field: value.field as TailoringUserIssue['field'],
      reason: value.reason as TailoringUserIssue['reason'],
    };
  });
}

export function parseTailoringSessionList(raw: unknown): TailoringSessionListResponse {
  const value = object(raw, 'sessions');
  exact(value, ['items'], 'sessions');
  return {
    items: array(value.items, 'sessions.items', 100).map((item, index) =>
      parseSession(item, `sessions.items[${index}]`),
    ),
  };
}

export function parseTailoringSessionDetail(
  raw: unknown,
): TailoringSessionDetailResponse {
  const value = object(raw, 'detail');
  exact(
    value,
    [
      'session',
      'versions',
      'selected_version',
      'content',
      'evidence',
      'latest_run',
      'source_available',
      'pdf_available',
    ],
    'detail',
  );
  const versions = array(value.versions, 'detail.versions', 10_000).map(
    (item, index) => parseVersion(item, `detail.versions[${index}]`),
  );
  const selected =
    value.selected_version === null
      ? null
      : parseVersion(value.selected_version, 'detail.selected_version');
  if (selected !== null && !versions.some((item) => item.id === selected.id)) {
    throw new Error('detail.selected_version must belong to versions');
  }
  if ((selected === null) !== (value.content === null)) {
    throw new Error('detail content/version coupling is invalid');
  }
  return {
    session: parseSession(value.session, 'detail.session'),
    versions,
    selected_version: selected,
    content: value.content === null ? null : parseTailoredContent(value.content),
    evidence: array(value.evidence, 'detail.evidence', 20_000).map((item, index) =>
      parseEvidence(item, `detail.evidence[${index}]`),
    ),
    latest_run: parseRun(value.latest_run, 'detail.latest_run'),
    source_available: bool(value.source_available, 'detail.source_available'),
    pdf_available: bool(value.pdf_available, 'detail.pdf_available'),
  };
}

export function parseTailoringMutationResponse(
  raw: unknown,
): TailoringVersionMutationResponse {
  const value = object(raw, 'version');
  exact(
    value,
    ['outcome', 'session_id', 'version_id', 'version_number', 'currentness'],
    'version',
  );
  if (value.currentness !== 'current') throw new Error('version currentness invalid');
  if (value.outcome !== 'version_created' && value.outcome !== 'no_change') {
    throw new Error('version outcome invalid');
  }
  return {
    outcome: value.outcome,
    session_id: uuid(value.session_id, 'version.session_id'),
    version_id: uuid(value.version_id, 'version.version_id'),
    version_number: integer(value.version_number, 'version.version_number', 1),
    currentness: 'current',
  };
}

export function parseTailoringSseFrame(
  frame: SseWireFrame,
): TypedSseParseResult<TailoringSseEvent> {
  try {
    const raw = object(JSON.parse(frame.data) as unknown, 'tailoring event');
    exact(raw, ['event_id', 'run_id', 'timestamp', 'event', 'payload'], 'tailoring event');
    if (raw.event !== 'run_completed' && raw.event !== 'run_failed') {
      const event = parseSseEventData(raw) as TailoringSseEvent;
      if (frame.event !== null && frame.event !== event.event) throw new SseParseError('wire event name mismatch');
      if (frame.id !== null && frame.id.toLowerCase() !== event.event_id) throw new SseParseError('wire event id mismatch');
      return {ok: true, event};
    }
    if (raw.event === 'run_failed') {
      const payload = object(raw.payload, 'tailoring run_failed payload');
      const hasIssues = payload.issues !== undefined;
      exact(payload, hasIssues ? ['state', 'error_code', 'summary', 'issues'] : ['state', 'error_code', 'summary'], 'tailoring run_failed payload');
      if (payload.state !== 'failed') throw new SseParseError("run_failed requires state='failed'");
      const event: TailoringSseEvent = {
        event_id: uuid(raw.event_id, 'tailoring event.event_id'),
        run_id: uuid(raw.run_id, 'tailoring event.run_id'),
        timestamp: timestamp(raw.timestamp, 'tailoring event.timestamp'),
        event: 'run_failed',
        payload: {
          state: 'failed',
          error_code: text(payload.error_code, 'tailoring event.error_code', 120),
          summary: text(payload.summary, 'tailoring event.summary', 500),
          ...(hasIssues ? {issues: parseTailoringIssues(payload.issues)} : {}),
        },
      };
      if (frame.event !== null && frame.event !== event.event) throw new SseParseError('wire event name mismatch');
      if (frame.id !== null && frame.id.toLowerCase() !== event.event_id) throw new SseParseError('wire event id mismatch');
      return {ok: true, event};
    }
    const payload = object(raw.payload, 'tailoring run_completed payload');
    const outcome = payload.outcome;
    const hasOutcome = outcome !== undefined;
    exact(payload, hasOutcome ? ['state', 'outcome', 'version_id', 'version_number'] : ['state'], 'tailoring run_completed payload');
    if (payload.state !== 'completed') throw new SseParseError("run_completed requires state='completed'");
    if (hasOutcome && outcome !== 'version_created' && outcome !== 'no_change') throw new SseParseError('tailoring outcome invalid');
    if (!hasOutcome && (payload.version_id !== undefined || payload.version_number !== undefined)) throw new SseParseError('tailoring identity requires outcome');
    const event: TailoringSseEvent = {
      event_id: uuid(raw.event_id, 'tailoring event.event_id'),
      run_id: uuid(raw.run_id, 'tailoring event.run_id'),
      timestamp: timestamp(raw.timestamp, 'tailoring event.timestamp'),
      event: 'run_completed',
      payload: hasOutcome ? {
        state: 'completed',
        outcome: outcome as TailoringMutationOutcome,
        version_id: uuid(payload.version_id, 'tailoring event.version_id'),
        version_number: integer(payload.version_number, 'tailoring event.version_number', 1),
      } : {state: 'completed'},
    };
    if (frame.event !== null && frame.event !== event.event) throw new SseParseError('wire event name mismatch');
    if (frame.id !== null && frame.id.toLowerCase() !== event.event_id) throw new SseParseError('wire event id mismatch');
    return {ok: true, event};
  } catch (error) {
    return {ok: false, error: error instanceof SseParseError ? error : new SseParseError(error instanceof Error ? error.message : 'parse failed'), frame};
  }
}

export function parseTailoringDelete(raw: unknown): TailoringDeleteResponse {
  const value = object(raw, 'delete');
  exact(value, ['deleted_session_id'], 'delete');
  return {deleted_session_id: uuid(value.deleted_session_id, 'delete.deleted_session_id')};
}

export function asTailoringErrorCode(value: unknown): TailoringErrorCode | null {
  return typeof value === 'string' &&
    (TAILORING_ERROR_CODES as readonly string[]).includes(value)
    ? (value as TailoringErrorCode)
    : null;
}

export function parseCreateTailoredCvResultData(
  raw: JsonObject | null | undefined,
): CreateTailoredCvResultData | null {
  if (raw === null || raw === undefined) return null;
  try {
    exact(
      raw,
      ['outcome', 'session_id', 'version_id', 'status', 'currentness'],
      'create_tailored_cv',
    );
    if (raw.outcome !== 'version_created' || raw.status !== 'ready' || raw.currentness !== 'current') return null;
    return {
      outcome: 'version_created',
      session_id: uuid(raw.session_id, 'create_tailored_cv.session_id'),
      version_id: uuid(raw.version_id, 'create_tailored_cv.version_id'),
      status: 'ready',
      currentness: 'current',
    };
  } catch {
    return null;
  }
}

export function projectCreateTailoredCvResultData(
  toolName: string,
  raw: JsonObject | null | undefined,
): JsonObject | null {
  if (toolName !== CREATE_TAILORED_CV_TOOL_NAME) return null;
  const parsed = parseCreateTailoredCvResultData(raw);
  return parsed === null ? null : {...parsed};
}

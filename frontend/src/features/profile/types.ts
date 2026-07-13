/**
 * Typed frontend contracts for Plan 4 profile/CV public APIs.
 * Mirror backend AttachmentPublic / ProfileReadResponse / CvUploadResponse.
 * Never carries storage_path, raw PDF bytes, or secrets.
 */

export type AttachmentState = 'staged' | 'active' | 'failed';
export type CvUploadOutcome =
  | 'new'
  | 'existing_active'
  | 'existing_staged'
  | 'retry';

/** Safe public attachment metadata (no filesystem path). */
export type AttachmentPublic = {
  id: string;
  original_name: string;
  mime_type: 'application/pdf';
  size_bytes: number;
  page_count: number | null;
  state: AttachmentState;
  failure_code: string | null;
};

export type ProfileUploadSummary = {
  present: boolean;
  current_title: string | null;
};

export type DraftUploadSummary = {
  present: boolean;
  draft_id: 'current' | null;
  source_attachment_id: string | null;
};

/** POST /api/attachments/cv success body. */
export type CvUploadResponse = {
  attachment: AttachmentPublic;
  outcome: CvUploadOutcome;
  profile: ProfileUploadSummary | null;
  draft: DraftUploadSummary | null;
};

/**
 * Compact approved-profile fields used by the sidebar (not full schema dump).
 * Full profile JSON may be present from GET /api/profile; UI only surfaces
 * filename + presence state, never raw extraction text.
 */
export type CandidateProfileSummary = {
  summary: string;
  current_title: string | null;
};

export type JobPreferencesSummary = {
  target_roles: string[];
  preferred_locations: string[];
  acceptable_work_modes: string[];
  target_seniority: string[];
};

/** GET /api/profile body: explicit empty or active state. */
export type ProfileReadResponse = {
  present: boolean;
  profile: CandidateProfileSummary | null;
  preferences: JobPreferencesSummary | null;
  active_attachment: AttachmentPublic | null;
};

/** Pending PDF attachment for the chat composer (ID + display name only). */
export type PendingPdfAttachment = {
  attachmentId: string;
  displayName: string;
};

export type ProfileApiParseError = {
  code: string;
  summary: string;
};

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

const ATTACHMENT_STATES: ReadonlySet<string> = new Set([
  'staged',
  'active',
  'failed',
]);

const UPLOAD_OUTCOMES: ReadonlySet<string> = new Set([
  'new',
  'existing_active',
  'existing_staged',
  'retry',
]);

export function parseAttachmentPublic(raw: unknown): AttachmentPublic {
  if (!isObject(raw)) {
    throw new Error('attachment must be an object');
  }
  const id = asString(raw.id);
  const original_name = asString(raw.original_name);
  const mime_type = asString(raw.mime_type);
  const size_bytes = asNumber(raw.size_bytes);
  const state = asString(raw.state);
  if (!id || !original_name || mime_type !== 'application/pdf') {
    throw new Error('attachment missing required safe fields');
  }
  if (size_bytes === null || size_bytes <= 0) {
    throw new Error('attachment size_bytes must be a positive number');
  }
  if (!state || !ATTACHMENT_STATES.has(state)) {
    throw new Error('attachment state is invalid');
  }
  // Reject path leakage at the client boundary.
  if ('storage_path' in raw) {
    throw new Error('attachment must not include storage_path');
  }
  const pageRaw = raw.page_count;
  const page_count =
    pageRaw === null || pageRaw === undefined ? null : asNumber(pageRaw);
  if (pageRaw !== null && pageRaw !== undefined && page_count === null) {
    throw new Error('attachment page_count must be number or null');
  }
  const failure_code =
    raw.failure_code === null || raw.failure_code === undefined
      ? null
      : asString(raw.failure_code);
  if (
    raw.failure_code !== null &&
    raw.failure_code !== undefined &&
    failure_code === null
  ) {
    throw new Error('attachment failure_code must be string or null');
  }
  return {
    id,
    original_name,
    mime_type: 'application/pdf',
    size_bytes,
    page_count,
    state: state as AttachmentState,
    failure_code,
  };
}

export function parseCvUploadResponse(raw: unknown): CvUploadResponse {
  if (!isObject(raw)) {
    throw new Error('CV upload response must be an object');
  }
  if ('storage_path' in raw) {
    throw new Error('CV upload response must not include storage_path');
  }
  const attachment = parseAttachmentPublic(raw.attachment);
  const outcome = asString(raw.outcome);
  if (!outcome || !UPLOAD_OUTCOMES.has(outcome)) {
    throw new Error('CV upload outcome is invalid');
  }
  let profile: ProfileUploadSummary | null = null;
  if (raw.profile !== null && raw.profile !== undefined) {
    if (!isObject(raw.profile)) {
      throw new Error('profile summary must be an object or null');
    }
    const present = asBoolean(raw.profile.present);
    if (present === null) {
      throw new Error('profile.present must be boolean');
    }
    const current_title =
      raw.profile.current_title === null ||
      raw.profile.current_title === undefined
        ? null
        : asString(raw.profile.current_title);
    if (
      raw.profile.current_title !== null &&
      raw.profile.current_title !== undefined &&
      current_title === null
    ) {
      throw new Error('profile.current_title must be string or null');
    }
    profile = {present, current_title};
  }
  let draft: DraftUploadSummary | null = null;
  if (raw.draft !== null && raw.draft !== undefined) {
    if (!isObject(raw.draft)) {
      throw new Error('draft summary must be an object or null');
    }
    const present = asBoolean(raw.draft.present);
    if (present === null) {
      throw new Error('draft.present must be boolean');
    }
    const draft_id_raw = raw.draft.draft_id;
    let draft_id: 'current' | null = null;
    if (draft_id_raw === null || draft_id_raw === undefined) {
      draft_id = null;
    } else if (draft_id_raw === 'current') {
      draft_id = 'current';
    } else {
      throw new Error("draft.draft_id must be 'current' or null");
    }
    const source_attachment_id =
      raw.draft.source_attachment_id === null ||
      raw.draft.source_attachment_id === undefined
        ? null
        : asString(raw.draft.source_attachment_id);
    if (
      raw.draft.source_attachment_id !== null &&
      raw.draft.source_attachment_id !== undefined &&
      source_attachment_id === null
    ) {
      throw new Error('draft.source_attachment_id must be string or null');
    }
    draft = {present, draft_id, source_attachment_id};
  }
  return {
    attachment,
    outcome: outcome as CvUploadOutcome,
    profile,
    draft,
  };
}

export function parseProfileReadResponse(raw: unknown): ProfileReadResponse {
  if (!isObject(raw)) {
    throw new Error('profile response must be an object');
  }
  if ('storage_path' in raw) {
    throw new Error('profile response must not include storage_path');
  }
  const present = asBoolean(raw.present);
  if (present === null) {
    throw new Error('profile.present must be boolean');
  }
  if (!present) {
    return {
      present: false,
      profile: null,
      preferences: null,
      active_attachment: null,
    };
  }
  if (!isObject(raw.profile)) {
    throw new Error('active profile payload missing');
  }
  const summary = asString(raw.profile.summary) ?? '';
  const current_title =
    raw.profile.current_title === null ||
    raw.profile.current_title === undefined
      ? null
      : asString(raw.profile.current_title);
  const profile: CandidateProfileSummary = {
    summary,
    current_title:
      current_title === null &&
      raw.profile.current_title !== null &&
      raw.profile.current_title !== undefined
        ? null
        : current_title,
  };
  if (
    raw.profile.current_title !== null &&
    raw.profile.current_title !== undefined &&
    typeof raw.profile.current_title !== 'string'
  ) {
    throw new Error('profile.current_title must be string or null');
  }

  let preferences: JobPreferencesSummary | null = null;
  if (raw.preferences !== null && raw.preferences !== undefined) {
    if (!isObject(raw.preferences)) {
      throw new Error('preferences must be an object or null');
    }
    const list = (key: string): string[] => {
      const v = raw.preferences && isObject(raw.preferences)
        ? raw.preferences[key]
        : undefined;
      if (!Array.isArray(v)) {
        return [];
      }
      return v.filter((x): x is string => typeof x === 'string');
    };
    preferences = {
      target_roles: list('target_roles'),
      preferred_locations: list('preferred_locations'),
      acceptable_work_modes: list('acceptable_work_modes'),
      target_seniority: list('target_seniority'),
    };
  }

  const active_attachment =
    raw.active_attachment === null || raw.active_attachment === undefined
      ? null
      : parseAttachmentPublic(raw.active_attachment);

  return {
    present: true,
    profile,
    preferences,
    active_attachment,
  };
}

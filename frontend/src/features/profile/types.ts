/**
 * Typed frontend contracts for Plan 4 profile/CV public APIs.
 * Mirror backend AttachmentPublic / ProfileReadResponse / CvUploadResponse.
 * Never carries storage_path, raw PDF bytes, or secrets.
 */

import {
  parseAttachmentPublic,
  parseConversationSummary,
  parseProfileListItem,
  type ConversationSummary,
  type ProfileListItem,
} from './conversationTypes';

export {parseAttachmentPublic} from './conversationTypes';

export type AttachmentState =
  | 'staged'
  | 'active'
  | 'archived'
  | 'failed'
  | 'deleting';
export type CvUploadOutcome =
  | 'new_pending'
  | 'retry_pending'
  | 'existing_pending'
  | 'existing_active'
  | 'existing_profile';

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
  profile_id?: string | null;
  current_title: string | null;
};

export type DraftUploadSummary = {
  present: boolean;
  draft_id: 'current' | null;
  source_attachment_id: string | null;
};

export type PendingProfileBootstrap = {
  profile: ProfileListItem;
  conversation: ConversationSummary;
  start_extraction: boolean;
};

/** POST /api/attachments/cv success body. */
export type CvUploadResponse = {
  attachment: AttachmentPublic;
  outcome: CvUploadOutcome;
  profile: ProfileUploadSummary | null;
  draft: DraftUploadSummary | null;
  bootstrap: PendingProfileBootstrap | null;
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

export type PendingProfileReview = {
  profile_id: string;
  revision: string;
  source: 'agent_update' | 'reextract';
  can_review: boolean;
};

/** GET /api/profile body: explicit empty or active state. */
export type ProfileReadResponse = {
  present: boolean;
  profile: CandidateProfileSummary | null;
  preferences: JobPreferencesSummary | null;
  active_attachment: AttachmentPublic | null;
  /** True when an unapproved profile draft exists (Save Profile still needed). */
  draft_present: boolean;
  /** Staged attachment backing the draft, when any (safe metadata only). */
  pending_attachment: AttachmentPublic | null;
  pending_review: PendingProfileReview | null;
};

/** Pending PDF attachment for the chat composer (ID + display name only). */
export type PendingPdfAttachment = {
  attachmentId: string;
  displayName: string;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function parsePendingProfileReview(raw: unknown): PendingProfileReview | null {
  if (raw === null || raw === undefined) {
    return null;
  }
  if (!isObject(raw)) {
    throw new Error('pending_review must be an object or null');
  }
  exact(raw, ['profile_id', 'revision', 'source', 'can_review']);
  const profile_id = asString(raw.profile_id);
  const revision = asString(raw.revision);
  const can_review = asBoolean(raw.can_review);
  if (!profile_id) {
    throw new Error('pending_review.profile_id must be string');
  }
  if (!revision) {
    throw new Error('pending_review.revision must be string');
  }
  if (raw.source !== 'agent_update' && raw.source !== 'reextract') {
    throw new Error('pending_review.source is invalid');
  }
  if (can_review === null) {
    throw new Error('pending_review.can_review must be boolean');
  }
  return {
    profile_id,
    revision,
    source: raw.source,
    can_review,
  };
}

const UPLOAD_OUTCOMES: ReadonlySet<string> = new Set([
  'new_pending',
  'retry_pending',
  'existing_pending',
  'existing_active',
  'existing_profile',
]);

function exact(raw: Record<string, unknown>, keys: readonly string[]): void {
  const expected = new Set(keys);
  if (
    Object.keys(raw).some((key) => !expected.has(key)) ||
    keys.some((key) => !(key in raw))
  ) {
    throw new Error('unexpected response field');
  }
}

export function parseCvUploadResponse(raw: unknown): CvUploadResponse {
  if (!isObject(raw)) {
    throw new Error('CV upload response must be an object');
  }
  if ('storage_path' in raw) {
    throw new Error('CV upload response must not include storage_path');
  }
  exact(raw, ['attachment', 'outcome', 'profile', 'draft', 'bootstrap']);
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
    exact(raw.profile, ['present', 'profile_id', 'current_title']);
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
    profile = {
      present,
      profile_id:
        raw.profile.profile_id === null || raw.profile.profile_id === undefined
          ? null
          : asString(raw.profile.profile_id),
      current_title,
    };
    if (
      raw.profile.profile_id !== null &&
      raw.profile.profile_id !== undefined &&
      profile.profile_id === null
    ) {
      throw new Error('profile.profile_id must be string or null');
    }
  }
  let draft: DraftUploadSummary | null = null;
  if (raw.draft !== null && raw.draft !== undefined) {
    if (!isObject(raw.draft)) {
      throw new Error('draft summary must be an object or null');
    }
    exact(raw.draft, ['present', 'draft_id', 'source_attachment_id']);
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

  let bootstrap: PendingProfileBootstrap | null = null;
  if (raw.bootstrap !== null && raw.bootstrap !== undefined) {
    if (!isObject(raw.bootstrap)) {
      throw new Error('bootstrap must be an object or null');
    }
    exact(raw.bootstrap, ['profile', 'conversation', 'start_extraction']);
    const profileItem = parseProfileListItem(raw.bootstrap.profile);
    const conversation = parseConversationSummary(raw.bootstrap.conversation);
    const start_extraction = asBoolean(raw.bootstrap.start_extraction);
    if (start_extraction === null) {
      throw new Error('bootstrap.start_extraction must be boolean');
    }
    if (profileItem.state !== 'pending') {
      throw new Error('bootstrap profile must be pending');
    }
    if (conversation.profile_id !== profileItem.id) {
      throw new Error('bootstrap conversation owner mismatch');
    }
    bootstrap = {profile: profileItem, conversation, start_extraction};
  }

  const pendingOutcome =
    outcome === 'new_pending' ||
    outcome === 'retry_pending' ||
    outcome === 'existing_pending';
  if (pendingOutcome) {
    if (bootstrap === null || profile !== null) {
      throw new Error('pending upload outcome requires bootstrap only');
    }
    if (
      (outcome === 'new_pending' || outcome === 'retry_pending') &&
      !bootstrap.start_extraction
    ) {
      throw new Error('new and retry pending outcomes must start extraction');
    }
  } else {
    if (bootstrap !== null) {
      throw new Error('ready upload outcome cannot include bootstrap');
    }
    if (profile === null) {
      throw new Error('ready upload outcome requires profile summary');
    }
  }
  return {
    attachment,
    outcome: outcome as CvUploadOutcome,
    profile,
    draft,
    bootstrap,
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
  const draft_present = asBoolean(raw.draft_present) ?? false;
  const pending_attachment =
    raw.pending_attachment === null || raw.pending_attachment === undefined
      ? null
      : parseAttachmentPublic(raw.pending_attachment);
  const pending_review = parsePendingProfileReview(raw.pending_review);

  if (!present) {
    return {
      present: false,
      profile: null,
      preferences: null,
      active_attachment: null,
      draft_present,
      pending_attachment,
      pending_review,
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
    draft_present,
    pending_attachment,
    pending_review,
  };
}

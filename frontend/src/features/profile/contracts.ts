/**
 * Strict runtime-parsed public profile / CV upload contracts.
 * Source: Plan 4 §7.1, Master §14, backend app/schemas/profile.py + attachments.py.
 */

export const PROFILE_API_PATHS = {
  profile: "/api/profile",
  cv: "/api/profile/cv",
  upload: "/api/attachments/cv",
} as const;

/** Source-approved deterministic non-PII text for sidebar upload turns. */
export const SIDEBAR_PROFILE_TURN_TEXT =
  "Create a candidate profile draft from the attached CV." as const;

export type ProfilePresenceState = "none" | "active";

export interface SafeActiveAttachment {
  readonly id: string;
  readonly original_name: string;
  readonly mime_type: string;
  readonly size_bytes: number;
  readonly page_count: number | null;
  readonly state: string;
}

/**
 * Public GET /api/profile document.
 * Nested profile/preferences bodies are accepted as plain objects when present;
 * the envelope and active-attachment metadata are strictly validated.
 */
export interface ProfileResponse {
  readonly state: ProfilePresenceState;
  readonly profile: Record<string, unknown> | null;
  readonly preferences: Record<string, unknown> | null;
  readonly active_attachment: SafeActiveAttachment | null;
}

/** POST /api/attachments/cv success body. */
export interface StagedAttachmentResponse {
  readonly id: string;
  readonly original_name: string;
  readonly mime_type: string;
  readonly size_bytes: number;
  readonly page_count: number;
  readonly state: string;
}

export class ProfileContractError extends Error {
  readonly code: string;

  constructor(code: string, message?: string) {
    super(message ?? code);
    this.name = "ProfileContractError";
    this.code = code;
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new ProfileContractError("invalid_profile", `missing or invalid ${field}`);
  }
  return value;
}

function requireNonNegativeInt(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new ProfileContractError("invalid_profile", `missing or invalid ${field}`);
  }
  return Math.trunc(value);
}

function optionalNonNegativeInt(value: unknown, field: string): number | null {
  if (value === undefined || value === null) {
    return null;
  }
  return requireNonNegativeInt(value, field);
}

function parseSafeActiveAttachment(raw: unknown): SafeActiveAttachment {
  if (!isPlainObject(raw)) {
    throw new ProfileContractError("invalid_profile", "active_attachment invalid");
  }
  return {
    id: requireString(raw.id, "active_attachment.id"),
    original_name: requireString(raw.original_name, "active_attachment.original_name"),
    mime_type: requireString(raw.mime_type, "active_attachment.mime_type"),
    size_bytes: requireNonNegativeInt(raw.size_bytes, "active_attachment.size_bytes"),
    page_count: optionalNonNegativeInt(
      raw.page_count,
      "active_attachment.page_count",
    ),
    state: requireString(raw.state, "active_attachment.state"),
  };
}

/**
 * Parse GET /api/profile JSON. Rejects unknown state values and inconsistent
 * no-profile / active envelopes (mirrors backend presence rules).
 */
export function parseProfileResponse(raw: unknown): ProfileResponse {
  if (!isPlainObject(raw)) {
    throw new ProfileContractError("invalid_profile", "profile response invalid");
  }

  const state = raw.state;
  if (state !== "none" && state !== "active") {
    throw new ProfileContractError("invalid_profile", "invalid profile state");
  }

  const profileRaw = raw.profile;
  const preferencesRaw = raw.preferences;
  const attachmentRaw = raw.active_attachment;

  if (state === "none") {
    if (
      profileRaw !== null &&
      profileRaw !== undefined
    ) {
      throw new ProfileContractError(
        "invalid_profile",
        "no-profile state must not carry profile",
      );
    }
    if (preferencesRaw !== null && preferencesRaw !== undefined) {
      throw new ProfileContractError(
        "invalid_profile",
        "no-profile state must not carry preferences",
      );
    }
    if (attachmentRaw !== null && attachmentRaw !== undefined) {
      throw new ProfileContractError(
        "invalid_profile",
        "no-profile state must not carry active_attachment",
      );
    }
    return {
      state: "none",
      profile: null,
      preferences: null,
      active_attachment: null,
    };
  }

  if (!isPlainObject(profileRaw)) {
    throw new ProfileContractError(
      "invalid_profile",
      "active state requires profile object",
    );
  }

  let preferences: Record<string, unknown> | null = null;
  if (preferencesRaw !== null && preferencesRaw !== undefined) {
    if (!isPlainObject(preferencesRaw)) {
      throw new ProfileContractError("invalid_profile", "preferences invalid");
    }
    preferences = preferencesRaw;
  }

  let active_attachment: SafeActiveAttachment | null = null;
  if (attachmentRaw !== null && attachmentRaw !== undefined) {
    active_attachment = parseSafeActiveAttachment(attachmentRaw);
  }

  return {
    state: "active",
    profile: profileRaw,
    preferences,
    active_attachment,
  };
}

/** Parse POST /api/attachments/cv success JSON. */
export function parseStagedAttachmentResponse(
  raw: unknown,
): StagedAttachmentResponse {
  if (!isPlainObject(raw)) {
    throw new ProfileContractError("invalid_upload", "upload response invalid");
  }
  return {
    id: requireString(raw.id, "id"),
    original_name: requireString(raw.original_name, "original_name"),
    mime_type: requireString(raw.mime_type, "mime_type"),
    size_bytes: requireNonNegativeInt(raw.size_bytes, "size_bytes"),
    page_count: requireNonNegativeInt(raw.page_count, "page_count"),
    state: requireString(raw.state, "state"),
  };
}

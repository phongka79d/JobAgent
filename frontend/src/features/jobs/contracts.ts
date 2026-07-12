/**
 * Bounded saved-Job chat card contract (Plan 5).
 * Shared shape for live run_completed.saved_job and durable history
 * structured_payload. Presentation-free: no React imports.
 */

export const KIND_SAVED_JOB = "saved_job" as const;

export type SavedJobKind = typeof KIND_SAVED_JOB;

/** Display-only card fields — never raw JD, tool args, secrets, or stacks. */
export interface SavedJobCardPayload {
  readonly kind: SavedJobKind;
  readonly jobId: string;
  readonly title: string | null;
  readonly company: string | null;
  readonly location: string | null;
  readonly workMode: string | null;
  readonly employmentType: string | null;
  readonly jdQuality: string | null;
  readonly qualityReasonsPreview: readonly string[];
  readonly processingResult: string;
  readonly duplicateOutcome: string;
  readonly graphSyncStatus: string;
  readonly sourceUrl: string | null;
}

const MAX_TEXT = 256;
const MAX_REASONS = 5;
const MAX_URL = 2048;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalTrimmed(value: unknown, max = MAX_TEXT): string | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string") {
    return null;
  }
  const cleaned = value.trim().replace(/\s+/g, " ");
  if (!cleaned) {
    return null;
  }
  return cleaned.slice(0, max);
}

function requireToken(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`invalid ${field}`);
  }
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/-/g, "_")
    .replace(/\s+/g, "_");
  if (!cleaned || cleaned.length > 64) {
    throw new Error(`invalid ${field}`);
  }
  return cleaned;
}

function safePublicSourceUrl(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const cleaned = value.trim();
  if (!cleaned || cleaned.length > MAX_URL) {
    return null;
  }
  const lower = cleaned.toLowerCase();
  if (!lower.startsWith("http://") && !lower.startsWith("https://")) {
    return null;
  }
  // Reject credential userinfo in authority.
  try {
    const url = new URL(cleaned);
    if (url.username || url.password) {
      return null;
    }
    const host = url.hostname.toLowerCase();
    if (
      !host ||
      host === "localhost" ||
      host.endsWith(".localhost") ||
      host.endsWith(".local") ||
      host.endsWith(".internal") ||
      host === "metadata.google.internal" ||
      host.startsWith("127.") ||
      host.startsWith("10.") ||
      host.startsWith("192.168.") ||
      host.startsWith("169.254.") ||
      host === "0.0.0.0"
    ) {
      return null;
    }
  } catch {
    return null;
  }
  return cleaned;
}

function reasonsPreview(value: unknown): readonly string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const out: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") {
      continue;
    }
    const cleaned = item.trim().replace(/\s+/g, " ");
    if (!cleaned) {
      continue;
    }
    out.push(cleaned.slice(0, MAX_TEXT));
    if (out.length >= MAX_REASONS) {
      break;
    }
  }
  return out;
}

/**
 * Fail-closed parser for saved-job structured payloads (history + SSE).
 * Returns null when kind mismatches or required fields are missing/unsafe.
 */
export function parseSavedJobCardPayload(
  raw: unknown,
): SavedJobCardPayload | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  if (raw.kind !== KIND_SAVED_JOB) {
    return null;
  }
  const jobIdRaw = raw.job_id ?? raw.jobId;
  if (typeof jobIdRaw !== "string" || jobIdRaw.trim().length === 0) {
    return null;
  }
  const jobId = jobIdRaw.trim();
  // UUID-shaped public id only (no internal DB paths).
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      jobId,
    )
  ) {
    return null;
  }

  let processingResult: string;
  let duplicateOutcome: string;
  let graphSyncStatus: string;
  try {
    processingResult = requireToken(
      raw.processing_result ?? raw.processingResult,
      "processing_result",
    );
    duplicateOutcome = requireToken(
      raw.duplicate_outcome ?? raw.duplicateOutcome,
      "duplicate_outcome",
    );
    graphSyncStatus = requireToken(
      raw.graph_sync_status ?? raw.graphSyncStatus,
      "graph_sync_status",
    );
  } catch {
    return null;
  }

  return {
    kind: KIND_SAVED_JOB,
    jobId,
    title: optionalTrimmed(raw.title),
    company: optionalTrimmed(raw.company),
    location: optionalTrimmed(raw.location),
    workMode: optionalTrimmed(raw.work_mode ?? raw.workMode, 64),
    employmentType: optionalTrimmed(
      raw.employment_type ?? raw.employmentType,
      64,
    ),
    jdQuality: optionalTrimmed(raw.jd_quality ?? raw.jdQuality, 64),
    qualityReasonsPreview: reasonsPreview(
      raw.quality_reasons_preview ?? raw.qualityReasonsPreview,
    ),
    processingResult,
    duplicateOutcome,
    graphSyncStatus,
    sourceUrl: safePublicSourceUrl(raw.source_url ?? raw.sourceUrl),
  };
}

/** Human-readable labels for enumerated job status tokens. */
export function formatJobStatusLabel(token: string): string {
  const cleaned = token.trim().toLowerCase().replace(/_/g, " ");
  if (!cleaned) {
    return token;
  }
  return cleaned.replace(/\b\w/g, (ch) => ch.toUpperCase());
}

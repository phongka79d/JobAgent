/**
 * Bounded Job chat card contracts (Plan 5 saved_job + Plan 6 match_results).
 * Shared shape for live run_completed and durable history structured_payload.
 * Presentation-free: no React imports.
 */

export const KIND_SAVED_JOB = "saved_job" as const;
export const KIND_MATCH_RESULTS = "match_results" as const;

export type SavedJobKind = typeof KIND_SAVED_JOB;
export type MatchResultsKind = typeof KIND_MATCH_RESULTS;

/** Locked hybrid component names (Master §18.2 / Plan 6 §7.4). */
export const MATCH_COMPONENT_NAMES = [
  "semantic_similarity",
  "skill_score",
  "seniority_score",
  "experience_score",
  "location_score",
  "work_mode_score",
] as const;

export type MatchComponentName = (typeof MATCH_COMPONENT_NAMES)[number];

export const MATCH_RESULT_CONTRACT_VERSION = "match_result_v1" as const;

export const MAX_MATCH_RESULTS = 10;
export const MAX_MATCH_SKILL_ITEMS = 30;
export const MAX_EXPLANATION_LINES = 16;
export const MAX_EXPLANATION_LINE_LEN = 256;
export const MAX_RELATED_PATH_KEYS = 4;
export const MAX_COMPONENT_ENTRIES = MATCH_COMPONENT_NAMES.length;
/** Documented tolerance for effective weights summing to one. */
export const WEIGHT_SUM_TOLERANCE = 1e-6;

export type VisibleMatchKind =
  | "direct"
  | "verified_alias"
  | "verified_related"
  | "no_match";

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

export interface MatchComponentEntry {
  readonly name: MatchComponentName;
  readonly available: boolean;
  readonly value: number | null;
  readonly effectiveWeight: number | null;
}

export interface MatchSkillPath {
  readonly canonicalKey: string;
  readonly displayName: string;
  readonly matchKind: VisibleMatchKind;
  readonly strength: number;
  readonly relatedPath: readonly string[];
  readonly candidateCanonicalKey: string | null;
}

/** One transparent top-match result for chat cards. */
export interface MatchResultItem {
  readonly jobId: string;
  readonly title: string | null;
  readonly company: string | null;
  readonly location: string | null;
  readonly workMode: string | null;
  readonly finalScore: number;
  readonly quality: "full" | "partial";
  readonly components: readonly MatchComponentEntry[];
  readonly matchedRequiredSkills: readonly MatchSkillPath[];
  readonly relatedSkills: readonly MatchSkillPath[];
  readonly missingRequiredSkills: readonly MatchSkillPath[];
  readonly explanationLines: readonly string[];
  readonly sourceUrl: string | null;
  readonly seedConfigVersion: string;
  readonly contractVersion: string;
}

/** Bounded match-results card (live SSE + durable history). */
export interface MatchResultsCardPayload {
  readonly kind: MatchResultsKind;
  readonly contractVersion: string;
  readonly seedConfigVersion: string;
  readonly count: number;
  readonly results: readonly MatchResultItem[];
}

const MAX_TEXT = 256;
const MAX_REASONS = 5;
const MAX_URL = 2048;
const MAX_CANONICAL_KEY = 128;
const MAX_DISPLAY_NAME = 128;
const MAX_TITLE = 256;
const MAX_ORG = 256;
const MAX_LOCATION = 256;
const MAX_VERSION = 64;

const COMPONENT_NAME_SET = new Set<string>(MATCH_COMPONENT_NAMES);
const VISIBLE_MATCH_KINDS = new Set<VisibleMatchKind>([
  "direct",
  "verified_alias",
  "verified_related",
  "no_match",
]);
const JOB_UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

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

/**
 * Fail-closed public http(s) source URL helper shared by saved-job and match cards.
 * Rejects credentials, private hosts, and non-http schemes.
 */
export function safePublicSourceUrl(value: unknown): string | null {
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

function requireVersion(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`invalid ${field}`);
  }
  const cleaned = value.trim();
  if (!cleaned || cleaned.length > MAX_VERSION) {
    throw new Error(`invalid ${field}`);
  }
  return cleaned;
}

function requireUnitScore(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`invalid ${field}`);
  }
  if (value < 0 || value > 1) {
    throw new Error(`invalid ${field}`);
  }
  return value;
}

function requireJobId(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error("invalid job_id");
  }
  const jobId = value.trim();
  if (!JOB_UUID_RE.test(jobId)) {
    throw new Error("invalid job_id");
  }
  return jobId;
}

function parseSkillPath(
  raw: unknown,
  allowedKinds: ReadonlySet<VisibleMatchKind>,
): MatchSkillPath | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  const canonicalKey = optionalTrimmed(
    raw.canonical_key ?? raw.canonicalKey,
    MAX_CANONICAL_KEY,
  );
  const displayName = optionalTrimmed(
    raw.display_name ?? raw.displayName,
    MAX_DISPLAY_NAME,
  );
  if (!canonicalKey || !displayName) {
    return null;
  }
  const kindRaw = raw.match_kind ?? raw.matchKind;
  if (typeof kindRaw !== "string" || !VISIBLE_MATCH_KINDS.has(kindRaw as VisibleMatchKind)) {
    return null;
  }
  const matchKind = kindRaw as VisibleMatchKind;
  if (!allowedKinds.has(matchKind)) {
    return null;
  }
  let strength: number;
  try {
    strength = requireUnitScore(raw.strength, "strength");
  } catch {
    return null;
  }

  const pathRaw = raw.related_path ?? raw.relatedPath;
  const relatedPath: string[] = [];
  if (Array.isArray(pathRaw)) {
    for (const item of pathRaw) {
      if (typeof item !== "string") {
        continue;
      }
      const token = item.trim();
      if (!token) {
        continue;
      }
      relatedPath.push(token.slice(0, MAX_CANONICAL_KEY));
      if (relatedPath.length >= MAX_RELATED_PATH_KEYS) {
        break;
      }
    }
  }

  if (matchKind === "verified_related") {
    if (relatedPath.length < 2 || strength <= 0) {
      return null;
    }
  }
  if (
    (matchKind === "direct" || matchKind === "verified_alias") &&
    strength <= 0
  ) {
    return null;
  }
  if (matchKind === "no_match" && strength !== 0) {
    return null;
  }

  const candidateCanonicalKey = optionalTrimmed(
    raw.candidate_canonical_key ?? raw.candidateCanonicalKey,
    MAX_CANONICAL_KEY,
  );

  return {
    canonicalKey,
    displayName,
    matchKind,
    strength,
    relatedPath,
    candidateCanonicalKey,
  };
}

function parseSkillList(
  value: unknown,
  allowedKinds: ReadonlySet<VisibleMatchKind>,
): readonly MatchSkillPath[] | null {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    return null;
  }
  if (value.length > MAX_MATCH_SKILL_ITEMS) {
    return null;
  }
  const out: MatchSkillPath[] = [];
  for (const item of value) {
    const path = parseSkillPath(item, allowedKinds);
    if (path === null) {
      return null;
    }
    out.push(path);
  }
  return out;
}

function parseComponentEntry(raw: unknown): MatchComponentEntry | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  const nameRaw = raw.name;
  if (typeof nameRaw !== "string" || !COMPONENT_NAME_SET.has(nameRaw)) {
    return null;
  }
  const name = nameRaw as MatchComponentName;
  if (typeof raw.available !== "boolean") {
    return null;
  }
  if (!raw.available) {
    if (raw.value != null || raw.effective_weight != null || raw.effectiveWeight != null) {
      return null;
    }
    return {
      name,
      available: false,
      value: null,
      effectiveWeight: null,
    };
  }
  try {
    const value = requireUnitScore(raw.value, "value");
    const weightRaw = raw.effective_weight ?? raw.effectiveWeight;
    const effectiveWeight = requireUnitScore(weightRaw, "effective_weight");
    return { name, available: true, value, effectiveWeight };
  } catch {
    return null;
  }
}

function parseComponents(value: unknown): readonly MatchComponentEntry[] | null {
  if (!Array.isArray(value) || value.length !== MAX_COMPONENT_ENTRIES) {
    return null;
  }
  const entries: MatchComponentEntry[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    const entry = parseComponentEntry(item);
    if (entry === null) {
      return null;
    }
    if (seen.has(entry.name)) {
      return null;
    }
    seen.add(entry.name);
    entries.push(entry);
  }
  for (const required of MATCH_COMPONENT_NAMES) {
    if (!seen.has(required)) {
      return null;
    }
  }
  const availableWeights = entries
    .filter((e) => e.available)
    .map((e) => e.effectiveWeight)
    .filter((w): w is number => typeof w === "number");
  if (availableWeights.length === 0) {
    return null;
  }
  const weightSum = availableWeights.reduce((a, b) => a + b, 0);
  if (Math.abs(weightSum - 1) > WEIGHT_SUM_TOLERANCE) {
    return null;
  }
  // Preserve locked COMPONENT_ORDER for deterministic presentation.
  const byName = new Map(entries.map((e) => [e.name, e]));
  return MATCH_COMPONENT_NAMES.map((n) => byName.get(n)!);
}

function parseExplanationLines(value: unknown): readonly string[] {
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
    out.push(cleaned.slice(0, MAX_EXPLANATION_LINE_LEN));
    if (out.length >= MAX_EXPLANATION_LINES) {
      break;
    }
  }
  return out;
}

function parseMatchResultItem(raw: unknown): MatchResultItem | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  let jobId: string;
  let finalScore: number;
  let seedConfigVersion: string;
  let contractVersion: string;
  try {
    jobId = requireJobId(raw.job_id ?? raw.jobId);
    finalScore = requireUnitScore(raw.final_score ?? raw.finalScore, "final_score");
    seedConfigVersion = requireVersion(
      raw.seed_config_version ?? raw.seedConfigVersion,
      "seed_config_version",
    );
    contractVersion = requireVersion(
      raw.contract_version ?? raw.contractVersion,
      "contract_version",
    );
  } catch {
    return null;
  }

  const qualityRaw = raw.quality;
  if (qualityRaw !== "full" && qualityRaw !== "partial") {
    return null;
  }

  const components = parseComponents(raw.components);
  if (components === null) {
    return null;
  }

  const matchedRequiredSkills = parseSkillList(
    raw.matched_required_skills ?? raw.matchedRequiredSkills,
    new Set<VisibleMatchKind>(["direct", "verified_alias"]),
  );
  const relatedSkills = parseSkillList(
    raw.related_skills ?? raw.relatedSkills,
    new Set<VisibleMatchKind>(["verified_related"]),
  );
  const missingRequiredSkills = parseSkillList(
    raw.missing_required_skills ?? raw.missingRequiredSkills,
    new Set<VisibleMatchKind>(["no_match"]),
  );
  if (
    matchedRequiredSkills === null ||
    relatedSkills === null ||
    missingRequiredSkills === null
  ) {
    return null;
  }

  return {
    jobId,
    title: optionalTrimmed(raw.title, MAX_TITLE),
    company: optionalTrimmed(raw.company, MAX_ORG),
    location: optionalTrimmed(raw.location, MAX_LOCATION),
    workMode: optionalTrimmed(raw.work_mode ?? raw.workMode, 64),
    finalScore,
    quality: qualityRaw,
    components,
    matchedRequiredSkills,
    relatedSkills,
    missingRequiredSkills,
    explanationLines: parseExplanationLines(
      raw.explanation_lines ?? raw.explanationLines,
    ),
    sourceUrl: safePublicSourceUrl(raw.source_url ?? raw.sourceUrl),
    seedConfigVersion,
    contractVersion,
  };
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
  let jobId: string;
  try {
    jobId = requireJobId(raw.job_id ?? raw.jobId);
  } catch {
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

/**
 * Fail-closed parser for match_results structured payloads (history + SSE).
 * Returns null when kind mismatches, bounds fail, or inventory is incomplete.
 */
export function parseMatchResultsCardPayload(
  raw: unknown,
): MatchResultsCardPayload | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  if (raw.kind !== KIND_MATCH_RESULTS) {
    return null;
  }

  let contractVersion: string;
  let seedConfigVersion: string;
  try {
    contractVersion = requireVersion(
      raw.contract_version ?? raw.contractVersion,
      "contract_version",
    );
    seedConfigVersion = requireVersion(
      raw.seed_config_version ?? raw.seedConfigVersion,
      "seed_config_version",
    );
  } catch {
    return null;
  }

  const resultsRaw = raw.results;
  if (!Array.isArray(resultsRaw)) {
    return null;
  }
  if (resultsRaw.length > MAX_MATCH_RESULTS) {
    return null;
  }

  const countRaw = raw.count;
  if (
    typeof countRaw !== "number" ||
    !Number.isFinite(countRaw) ||
    Math.trunc(countRaw) !== countRaw ||
    countRaw !== resultsRaw.length
  ) {
    return null;
  }

  const results: MatchResultItem[] = [];
  for (const item of resultsRaw) {
    const parsed = parseMatchResultItem(item);
    if (parsed === null) {
      return null;
    }
    if (parsed.contractVersion !== contractVersion) {
      return null;
    }
    if (parsed.seedConfigVersion !== seedConfigVersion) {
      return null;
    }
    results.push(parsed);
  }

  return {
    kind: KIND_MATCH_RESULTS,
    contractVersion,
    seedConfigVersion,
    count: results.length,
    results,
  };
}

/**
 * Serialize a validated match card to snake_case wire keys for message storage.
 * Identical live/history hydration re-parses this shape.
 */
export function matchResultsToStructuredPayload(
  card: MatchResultsCardPayload,
): Record<string, unknown> {
  return {
    kind: KIND_MATCH_RESULTS,
    contract_version: card.contractVersion,
    seed_config_version: card.seedConfigVersion,
    count: card.count,
    results: card.results.map((r) => ({
      job_id: r.jobId,
      title: r.title,
      company: r.company,
      location: r.location,
      work_mode: r.workMode,
      final_score: r.finalScore,
      quality: r.quality,
      components: r.components.map((c) => ({
        name: c.name,
        available: c.available,
        value: c.value,
        effective_weight: c.effectiveWeight,
      })),
      matched_required_skills: r.matchedRequiredSkills.map((s) => ({
        canonical_key: s.canonicalKey,
        display_name: s.displayName,
        match_kind: s.matchKind,
        strength: s.strength,
        related_path: [...s.relatedPath],
        candidate_canonical_key: s.candidateCanonicalKey,
      })),
      related_skills: r.relatedSkills.map((s) => ({
        canonical_key: s.canonicalKey,
        display_name: s.displayName,
        match_kind: s.matchKind,
        strength: s.strength,
        related_path: [...s.relatedPath],
        candidate_canonical_key: s.candidateCanonicalKey,
      })),
      missing_required_skills: r.missingRequiredSkills.map((s) => ({
        canonical_key: s.canonicalKey,
        display_name: s.displayName,
        match_kind: s.matchKind,
        strength: s.strength,
        related_path: [...s.relatedPath],
        candidate_canonical_key: s.candidateCanonicalKey,
      })),
      explanation_lines: [...r.explanationLines],
      source_url: r.sourceUrl,
      seed_config_version: r.seedConfigVersion,
      contract_version: r.contractVersion,
    })),
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

/** Format a unit score in [0,1] as a stable percent string (e.g. "85%"). */
export function formatMatchScore(score: number): string {
  if (!Number.isFinite(score)) {
    return "—";
  }
  const clamped = Math.min(1, Math.max(0, score));
  return `${Math.round(clamped * 100)}%`;
}

/** Human labels for locked score component names. */
export function formatComponentLabel(name: string): string {
  switch (name) {
    case "semantic_similarity":
      return "Semantic similarity";
    case "skill_score":
      return "Skill score";
    case "seniority_score":
      return "Seniority";
    case "experience_score":
      return "Experience";
    case "location_score":
      return "Location";
    case "work_mode_score":
      return "Work mode";
    default:
      return formatJobStatusLabel(name);
  }
}

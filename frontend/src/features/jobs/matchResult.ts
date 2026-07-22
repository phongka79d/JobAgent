/**
 * Strict compact match_jobs ToolResult projection (Plan 6 §7.9 / Master §15.5).
 * Backend schemas/matching.py is the sole JSON authority — no parallel shape.
 * Parses durable ToolResult.data only; never re-sorts; at most 10 results.
 */

import type {JsonObject, JsonValue} from '../chat/types';
import {safeHttpUrl} from './types';

export const MATCH_JOBS_TOOL_NAME = 'match_jobs' as const;

export type JobWorkMode = 'remote' | 'hybrid' | 'onsite' | 'unknown';

export type MatchSkillMatchType = 'direct' | 'related';

export const JOB_WORK_MODES: readonly JobWorkMode[] = [
  'remote',
  'hybrid',
  'onsite',
  'unknown',
] as const;

/** Exact MatchJobsResultData keys (backend compact contract). */
export const MATCH_JOBS_RESULT_DATA_KEYS = [
  'results',
  'count',
  'limit',
] as const;

const MATCH_RESULT_KEYS = [
  'job_id',
  'title',
  'company',
  'location',
  'work_mode',
  'source_url',
  'final_score',
  'quality_multiplier',
  'components',
  'effective_weights',
  'matched_required_skills',
  'matched_preferred_skills',
  'related_skills',
  'missing_required_skills',
  'summary',
] as const;

const COMPONENT_KEYS = [
  'semantic_similarity',
  'skill_score',
  'seniority_score',
  'experience_score',
  'location_score',
  'work_mode_score',
] as const;

const SKILL_EVIDENCE_KEYS = [
  'job_skill_key',
  'job_skill_display_name',
  'match_type',
  'strength',
  'candidate_skill_key',
  'candidate_skill_display_name',
  'job_evidence',
  'candidate_evidence',
  'relationship_from_key',
  'relationship_to_key',
  'relationship_weight',
  'relationship_source',
] as const;

const MISSING_SKILL_KEYS = [
  'job_skill_key',
  'job_skill_display_name',
  'job_evidence',
] as const;

const MATCH_JOBS_RESULT_KEY_SET: ReadonlySet<string> = new Set(
  MATCH_JOBS_RESULT_DATA_KEYS,
);
const MATCH_RESULT_KEY_SET: ReadonlySet<string> = new Set(MATCH_RESULT_KEYS);
const COMPONENT_KEY_SET: ReadonlySet<string> = new Set(COMPONENT_KEYS);
const SKILL_EVIDENCE_KEY_SET: ReadonlySet<string> = new Set(SKILL_EVIDENCE_KEYS);
const MISSING_SKILL_KEY_SET: ReadonlySet<string> = new Set(MISSING_SKILL_KEYS);

/** Ordered component display labels (backend key → UI label). */
export type MatchComponentKey = (typeof COMPONENT_KEYS)[number];

export interface CompactMatchSkillEvidence {
  jobSkillKey: string;
  jobSkillDisplayName: string;
  matchType: MatchSkillMatchType;
  strength: number;
  candidateSkillKey: string;
  candidateSkillDisplayName: string;
  jobEvidence: string[];
  candidateEvidence: string[];
  relationshipFromKey: string | null;
  relationshipToKey: string | null;
  relationshipWeight: number | null;
  relationshipSource: string | null;
}

export interface CompactMissingRequiredSkill {
  jobSkillKey: string;
  jobSkillDisplayName: string;
  jobEvidence: string[];
}

export interface CompactMatchComponents {
  semanticSimilarity: number;
  skillScore: number | null;
  seniorityScore: number | null;
  experienceScore: number | null;
  locationScore: number | null;
  workModeScore: number | null;
}

export interface CompactMatchResult {
  jobId: string;
  title: string | null;
  company: string | null;
  location: string | null;
  workMode: JobWorkMode;
  sourceUrl: string | null;
  finalScore: number;
  qualityMultiplier: number;
  components: CompactMatchComponents;
  /** Effective weights for available components only (backend order preserved). */
  effectiveWeights: ReadonlyArray<{key: MatchComponentKey; weight: number}>;
  matchedRequiredSkills: CompactMatchSkillEvidence[];
  matchedPreferredSkills: CompactMatchSkillEvidence[];
  relatedSkills: CompactMatchSkillEvidence[];
  missingRequiredSkills: CompactMissingRequiredSkill[];
  summary: string;
}

export interface CompactMatchJobsResult {
  results: CompactMatchResult[];
  count: number;
  limit: number;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(
  data: Record<string, unknown>,
  allowed: ReadonlySet<string>,
): boolean {
  for (const key of Object.keys(data)) {
    if (!allowed.has(key)) {
      return false;
    }
  }
  return true;
}

function asFiniteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function asNullableFiniteNumber(value: unknown): number | null | undefined {
  if (value === null) {
    return null;
  }
  return asFiniteNumber(value);
}

function asNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== 'string' || value.trim() === '') {
    return undefined;
  }
  return value;
}

function asNullableString(value: unknown): string | null | undefined {
  if (value === null) {
    return null;
  }
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== 'string') {
    return undefined;
  }
  return value;
}

function asStringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const out: string[] = [];
  for (const item of value) {
    if (typeof item !== 'string') {
      return undefined;
    }
    out.push(item);
  }
  return out;
}

function allowlistObject(
  data: Record<string, unknown>,
  keys: readonly string[],
): JsonObject {
  const out: JsonObject = {};
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(data, key)) {
      out[key] = data[key] as JsonValue;
    }
  }
  return out;
}

function parseStringListField(
  data: Record<string, unknown>,
  key: string,
): string[] | undefined {
  if (!Object.prototype.hasOwnProperty.call(data, key)) {
    return undefined;
  }
  return asStringList(data[key]);
}

function parseSkillEvidence(
  value: unknown,
): CompactMatchSkillEvidence | null {
  if (!isObject(value) || !hasOnlyKeys(value, SKILL_EVIDENCE_KEY_SET)) {
    return null;
  }
  const jobSkillKey = asNonEmptyString(value.job_skill_key);
  const jobSkillDisplayName = asNonEmptyString(value.job_skill_display_name);
  const matchTypeRaw = value.match_type;
  if (
    matchTypeRaw !== 'direct' &&
    matchTypeRaw !== 'related'
  ) {
    return null;
  }
  const strength = asFiniteNumber(value.strength);
  const candidateSkillKey = asNonEmptyString(value.candidate_skill_key);
  const candidateSkillDisplayName = asNonEmptyString(
    value.candidate_skill_display_name,
  );
  const jobEvidence = parseStringListField(value, 'job_evidence');
  const candidateEvidence = parseStringListField(value, 'candidate_evidence');
  if (
    jobSkillKey === undefined ||
    jobSkillDisplayName === undefined ||
    strength === undefined ||
    candidateSkillKey === undefined ||
    candidateSkillDisplayName === undefined ||
    jobEvidence === undefined ||
    candidateEvidence === undefined
  ) {
    return null;
  }

  for (const relKey of [
    'relationship_from_key',
    'relationship_to_key',
    'relationship_weight',
    'relationship_source',
  ] as const) {
    if (!Object.prototype.hasOwnProperty.call(value, relKey)) {
      return null;
    }
  }

  const relationshipFromKey = asNullableString(value.relationship_from_key);
  const relationshipToKey = asNullableString(value.relationship_to_key);
  const relationshipWeight = asNullableFiniteNumber(value.relationship_weight);
  const relationshipSource = asNullableString(value.relationship_source);
  if (
    relationshipFromKey === undefined ||
    relationshipToKey === undefined ||
    relationshipWeight === undefined ||
    relationshipSource === undefined
  ) {
    return null;
  }

  if (matchTypeRaw === 'direct') {
    if (
      relationshipFromKey !== null ||
      relationshipToKey !== null ||
      relationshipWeight !== null ||
      relationshipSource !== null
    ) {
      return null;
    }
  } else {
    if (
      relationshipFromKey === null ||
      relationshipFromKey.trim() === '' ||
      relationshipToKey === null ||
      relationshipToKey.trim() === '' ||
      relationshipWeight === null ||
      relationshipSource === null ||
      relationshipSource.trim() === ''
    ) {
      return null;
    }
  }

  return {
    jobSkillKey,
    jobSkillDisplayName,
    matchType: matchTypeRaw,
    strength,
    candidateSkillKey,
    candidateSkillDisplayName,
    jobEvidence,
    candidateEvidence,
    relationshipFromKey:
      relationshipFromKey === null || relationshipFromKey.trim() === ''
        ? null
        : relationshipFromKey,
    relationshipToKey:
      relationshipToKey === null || relationshipToKey.trim() === ''
        ? null
        : relationshipToKey,
    relationshipWeight,
    relationshipSource:
      relationshipSource === null || relationshipSource.trim() === ''
        ? null
        : relationshipSource,
  };
}

function parseMissingSkill(
  value: unknown,
): CompactMissingRequiredSkill | null {
  if (!isObject(value) || !hasOnlyKeys(value, MISSING_SKILL_KEY_SET)) {
    return null;
  }
  const jobSkillKey = asNonEmptyString(value.job_skill_key);
  const jobSkillDisplayName = asNonEmptyString(value.job_skill_display_name);
  const jobEvidence = parseStringListField(value, 'job_evidence');
  if (
    jobSkillKey === undefined ||
    jobSkillDisplayName === undefined ||
    jobEvidence === undefined
  ) {
    return null;
  }
  return {jobSkillKey, jobSkillDisplayName, jobEvidence};
}

function parseSkillEvidenceList(
  value: unknown,
): CompactMatchSkillEvidence[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const out: CompactMatchSkillEvidence[] = [];
  for (const item of value) {
    const parsed = parseSkillEvidence(item);
    if (parsed === null) {
      return null;
    }
    out.push(parsed);
  }
  return out;
}

function parseMissingSkillList(
  value: unknown,
): CompactMissingRequiredSkill[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const out: CompactMissingRequiredSkill[] = [];
  for (const item of value) {
    const parsed = parseMissingSkill(item);
    if (parsed === null) {
      return null;
    }
    out.push(parsed);
  }
  return out;
}

function parseComponents(
  value: unknown,
): CompactMatchComponents | null {
  if (!isObject(value) || !hasOnlyKeys(value, COMPONENT_KEY_SET)) {
    return null;
  }
  for (const key of COMPONENT_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      return null;
    }
  }
  const semanticSimilarity = asFiniteNumber(value.semantic_similarity);
  if (semanticSimilarity === undefined) {
    return null;
  }
  const skillScore = asNullableFiniteNumber(value.skill_score);
  const seniorityScore = asNullableFiniteNumber(value.seniority_score);
  const experienceScore = asNullableFiniteNumber(value.experience_score);
  const locationScore = asNullableFiniteNumber(value.location_score);
  const workModeScore = asNullableFiniteNumber(value.work_mode_score);
  if (
    skillScore === undefined ||
    seniorityScore === undefined ||
    experienceScore === undefined ||
    locationScore === undefined ||
    workModeScore === undefined
  ) {
    return null;
  }
  return {
    semanticSimilarity,
    skillScore,
    seniorityScore,
    experienceScore,
    locationScore,
    workModeScore,
  };
}

function parseEffectiveWeights(
  value: unknown,
): ReadonlyArray<{key: MatchComponentKey; weight: number}> | null {
  if (!isObject(value)) {
    return null;
  }
  const out: {key: MatchComponentKey; weight: number}[] = [];
  // Preserve object insertion order from backend JSON (never re-sort).
  for (const key of Object.keys(value)) {
    if (!COMPONENT_KEY_SET.has(key)) {
      return null;
    }
    const weight = asFiniteNumber(value[key]);
    if (weight === undefined) {
      return null;
    }
    out.push({key: key as MatchComponentKey, weight});
  }
  return out;
}

function parseNullableDisplayString(
  data: Record<string, unknown>,
  key: string,
): string | null | undefined {
  if (!Object.prototype.hasOwnProperty.call(data, key)) {
    return undefined;
  }
  const raw = asNullableString(data[key]);
  if (raw === undefined) {
    return undefined;
  }
  if (raw === null || raw.trim() === '') {
    return null;
  }
  return raw;
}

/**
 * Strict parse of one compact MatchResult object.
 * Returns null on any vocabulary/type/extra-key failure.
 */
export function parseMatchResult(
  data: unknown,
): CompactMatchResult | null {
  if (!isObject(data) || !hasOnlyKeys(data, MATCH_RESULT_KEY_SET)) {
    return null;
  }
  for (const key of MATCH_RESULT_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(data, key)) {
      return null;
    }
  }

  const jobId = asNonEmptyString(data.job_id);
  if (jobId === undefined) {
    return null;
  }

  const title = parseNullableDisplayString(data, 'title');
  const company = parseNullableDisplayString(data, 'company');
  const location = parseNullableDisplayString(data, 'location');
  if (
    title === undefined ||
    company === undefined ||
    location === undefined
  ) {
    return null;
  }

  const workModeRaw = data.work_mode;
  if (
    typeof workModeRaw !== 'string' ||
    !(JOB_WORK_MODES as readonly string[]).includes(workModeRaw)
  ) {
    return null;
  }

  const sourceUrlRaw = asNullableString(data.source_url);
  if (sourceUrlRaw === undefined) {
    return null;
  }

  const finalScore = asFiniteNumber(data.final_score);
  const qualityMultiplier = asFiniteNumber(data.quality_multiplier);
  if (finalScore === undefined || qualityMultiplier === undefined) {
    return null;
  }

  const components = parseComponents(data.components);
  const effectiveWeights = parseEffectiveWeights(data.effective_weights);
  const matchedRequiredSkills = parseSkillEvidenceList(
    data.matched_required_skills,
  );
  const matchedPreferredSkills = parseSkillEvidenceList(
    data.matched_preferred_skills,
  );
  const relatedSkills = parseSkillEvidenceList(data.related_skills);
  const missingRequiredSkills = parseMissingSkillList(
    data.missing_required_skills,
  );
  const summary = asNonEmptyString(data.summary);

  if (
    components === null ||
    effectiveWeights === null ||
    matchedRequiredSkills === null ||
    matchedPreferredSkills === null ||
    relatedSkills === null ||
    missingRequiredSkills === null ||
    summary === undefined
  ) {
    return null;
  }

  return {
    jobId,
    title,
    company,
    location,
    workMode: workModeRaw as JobWorkMode,
    sourceUrl: safeHttpUrl(sourceUrlRaw),
    finalScore,
    qualityMultiplier,
    components,
    effectiveWeights,
    matchedRequiredSkills,
    matchedPreferredSkills,
    relatedSkills,
    missingRequiredSkills,
    summary,
  };
}

/**
 * Strict parse of compact match_jobs ToolResult.data.
 * Accepts at most 10 results; preserves backend array order (no sort).
 * Requires count === results.length and count <= limit.
 */
export function parseMatchJobsResultData(
  data: JsonObject | null | undefined,
): CompactMatchJobsResult | null {
  if (!isObject(data) || !hasOnlyKeys(data, MATCH_JOBS_RESULT_KEY_SET)) {
    return null;
  }
  for (const key of MATCH_JOBS_RESULT_DATA_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(data, key)) {
      return null;
    }
  }

  const count = asFiniteNumber(data.count);
  const limit = asFiniteNumber(data.limit);
  if (
    count === undefined ||
    limit === undefined ||
    !Number.isInteger(count) ||
    !Number.isInteger(limit) ||
    count < 0 ||
    limit < 1 ||
    limit > 10
  ) {
    return null;
  }

  if (!Array.isArray(data.results)) {
    return null;
  }

  // Parse in backend order; cap at 10 for display safety.
  const rawResults = data.results.slice(0, 10);
  if (data.results.length > 10) {
    // Backend must not exceed 10; reject oversized payloads rather than truncate silently.
    return null;
  }

  const results: CompactMatchResult[] = [];
  for (const item of rawResults) {
    const parsed = parseMatchResult(item);
    if (parsed === null) {
      return null;
    }
    results.push(parsed);
  }

  if (count !== results.length || count > limit) {
    return null;
  }

  return {results, count, limit};
}

/**
 * Deep allowlist of MatchJobsResultData for durable history resultData.
 * Strips unknown keys; returns null when the slim payload fails exact parse.
 */
function allowlistMatchJobsResultData(
  data: Record<string, unknown>,
): JsonObject | null {
  if (!Array.isArray(data.results)) {
    return null;
  }
  const slimResults: JsonValue[] = [];
  for (const item of data.results) {
    if (!isObject(item)) {
      return null;
    }
    const slimItem = allowlistObject(item, MATCH_RESULT_KEYS);
    if (isObject(item.components)) {
      slimItem.components = allowlistObject(
        item.components as Record<string, unknown>,
        COMPONENT_KEYS,
      );
    }
    if (isObject(item.effective_weights)) {
      const weights: JsonObject = {};
      for (const key of Object.keys(
        item.effective_weights as Record<string, unknown>,
      )) {
        if (COMPONENT_KEY_SET.has(key)) {
          weights[key] = (item.effective_weights as Record<string, unknown>)[
            key
          ] as JsonValue;
        }
      }
      slimItem.effective_weights = weights;
    }
    for (const listKey of [
      'matched_required_skills',
      'matched_preferred_skills',
      'related_skills',
    ] as const) {
      const list = item[listKey];
      if (!Array.isArray(list)) {
        continue;
      }
      slimItem[listKey] = list.map((entry) =>
        isObject(entry)
          ? allowlistObject(entry, SKILL_EVIDENCE_KEYS)
          : entry,
      ) as JsonValue;
    }
    if (Array.isArray(item.missing_required_skills)) {
      slimItem.missing_required_skills = item.missing_required_skills.map(
        (entry) =>
          isObject(entry)
            ? allowlistObject(entry, MISSING_SKILL_KEYS)
            : entry,
      ) as JsonValue;
    }
    slimResults.push(slimItem);
  }
  return {
    results: slimResults,
    count: data.count as JsonValue,
    limit: data.limit as JsonValue,
  };
}

/**
 * Durable history boundary projection for match_jobs ToolResult.data.
 * Unrelated tools return null (caller may chain save_job projection).
 */
export function projectMatchJobsResultData(
  toolName: string,
  data: JsonObject | null | undefined,
): JsonObject | null {
  if (toolName !== MATCH_JOBS_TOOL_NAME) {
    return null;
  }
  if (!isObject(data)) {
    return null;
  }
  const slim = allowlistMatchJobsResultData(data);
  if (slim === null || parseMatchJobsResultData(slim) === null) {
    return null;
  }
  return slim;
}

export function isMatchJobsToolName(toolName: string): boolean {
  return toolName === MATCH_JOBS_TOOL_NAME;
}

/**
 * Display-only score formatting. Never used for ordering.
 * Rounds unrounded backend floats for human-readable percentage.
 */
export function formatDisplayScore(score: number): string {
  const pct = Math.round(score * 1000) / 10;
  return `${pct.toFixed(1)}%`;
}

/**
 * Display-only component value for ProgressBar (0–100 scale).
 * Null/unavailable callers should not invoke this for order decisions.
 */
export function formatComponentProgressValue(score: number): number {
  return Math.round(score * 1000) / 10;
}

/** Display-only weight percentage. */
export function formatDisplayWeight(weight: number): string {
  const pct = Math.round(weight * 1000) / 10;
  return `${pct.toFixed(1)}%`;
}

/** Display-only quality multiplier. */
export function formatQualityMultiplier(value: number): string {
  return value.toFixed(2);
}

/** Resolve component score by backend key from parsed DTO. */
export function componentScoreForKey(
  components: CompactMatchComponents,
  key: MatchComponentKey,
): number | null {
  switch (key) {
    case 'semantic_similarity':
      return components.semanticSimilarity;
    case 'skill_score':
      return components.skillScore;
    case 'seniority_score':
      return components.seniorityScore;
    case 'experience_score':
      return components.experienceScore;
    case 'location_score':
      return components.locationScore;
    case 'work_mode_score':
      return components.workModeScore;
    default: {
      const _exhaustive: never = key;
      return _exhaustive;
    }
  }
}

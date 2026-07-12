/**
 * Shared test fixtures for match card / score breakdown (no React).
 */

import {
  KIND_MATCH_RESULTS,
  MATCH_COMPONENT_NAMES,
  MATCH_RESULT_CONTRACT_VERSION,
  type MatchComponentEntry,
  type MatchResultItem,
  type MatchResultsCardPayload,
} from "../contracts";

export const MATCH_JOB_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
export const MATCH_SEED = "hybrid_seed_v1";

const DEFAULT_WEIGHTS: Record<string, [number, number]> = {
  semantic_similarity: [0.9, 0.3],
  skill_score: [0.8, 0.4],
  seniority_score: [1.0, 0.1],
  experience_score: [1.0, 0.1],
  location_score: [1.0, 0.05],
  work_mode_score: [1.0, 0.05],
};

export function fullComponents(
  overrides?: Partial<Record<string, Partial<MatchComponentEntry>>>,
): readonly MatchComponentEntry[] {
  return MATCH_COMPONENT_NAMES.map((name) => {
    const [value, weight] = DEFAULT_WEIGHTS[name] ?? [0.5, 1 / 6];
    const o = overrides?.[name];
    if (o?.available === false) {
      return {
        name,
        available: false,
        value: null,
        effectiveWeight: null,
      };
    }
    return {
      name,
      available: true,
      value: o?.value ?? value,
      effectiveWeight: o?.effectiveWeight ?? weight,
    };
  });
}

export function sampleMatchResult(
  partial?: Partial<MatchResultItem>,
): MatchResultItem {
  return {
    jobId: MATCH_JOB_ID,
    title: "Backend Engineer",
    company: "Acme Corp",
    location: "Remote",
    workMode: "remote",
    finalScore: 0.85,
    quality: "full",
    components: fullComponents(),
    matchedRequiredSkills: [
      {
        canonicalKey: "python",
        displayName: "Python",
        matchKind: "direct",
        strength: 1.0,
        relatedPath: [],
        candidateCanonicalKey: null,
      },
    ],
    relatedSkills: [
      {
        canonicalKey: "kubernetes",
        displayName: "Kubernetes",
        matchKind: "verified_related",
        strength: 0.6,
        relatedPath: ["python", "kubernetes"],
        candidateCanonicalKey: "python",
      },
    ],
    missingRequiredSkills: [
      {
        canonicalKey: "java",
        displayName: "Java",
        matchKind: "no_match",
        strength: 0.0,
        relatedPath: [],
        candidateCanonicalKey: null,
      },
    ],
    explanationLines: ["Semantic similarity: 0.9 (effective weight 0.3)"],
    sourceUrl: "https://example.com/jobs/backend",
    seedConfigVersion: MATCH_SEED,
    contractVersion: MATCH_RESULT_CONTRACT_VERSION,
    ...partial,
  };
}

export function sampleMatchCard(
  partial?: Partial<MatchResultsCardPayload>,
  results?: readonly MatchResultItem[],
): MatchResultsCardPayload {
  const list = results ?? [sampleMatchResult()];
  return {
    kind: KIND_MATCH_RESULTS,
    contractVersion: MATCH_RESULT_CONTRACT_VERSION,
    seedConfigVersion: MATCH_SEED,
    count: list.length,
    results: list,
    ...partial,
    // Keep count aligned when only results overridden via partial.
    ...(partial?.results
      ? { count: partial.results.length, results: partial.results }
      : {}),
  };
}

/** Wire-shape (snake_case) payload matching backend MatchResultsCardPayload dump. */
export function sampleMatchWire(
  jobId: string = MATCH_JOB_ID,
  score: number = 0.85,
): Record<string, unknown> {
  const components = MATCH_COMPONENT_NAMES.map((name) => {
    const [value, weight] = DEFAULT_WEIGHTS[name] ?? [0.5, 1 / 6];
    return {
      name,
      available: true,
      value,
      effective_weight: weight,
    };
  });
  return {
    kind: KIND_MATCH_RESULTS,
    contract_version: MATCH_RESULT_CONTRACT_VERSION,
    seed_config_version: MATCH_SEED,
    count: 1,
    results: [
      {
        job_id: jobId,
        title: "Backend Engineer",
        company: "Acme Corp",
        location: "Remote",
        work_mode: "remote",
        final_score: score,
        quality: "full",
        components,
        matched_required_skills: [
          {
            canonical_key: "python",
            display_name: "Python",
            match_kind: "direct",
            strength: 1.0,
            related_path: [],
            candidate_canonical_key: null,
          },
        ],
        related_skills: [
          {
            canonical_key: "kubernetes",
            display_name: "Kubernetes",
            match_kind: "verified_related",
            strength: 0.6,
            related_path: ["python", "kubernetes"],
            candidate_canonical_key: "python",
          },
        ],
        missing_required_skills: [
          {
            canonical_key: "java",
            display_name: "Java",
            match_kind: "no_match",
            strength: 0.0,
            related_path: [],
            candidate_canonical_key: null,
          },
        ],
        explanation_lines: [
          "Semantic similarity: 0.9 (effective weight 0.3)",
        ],
        source_url: "https://example.com/jobs/backend",
        seed_config_version: MATCH_SEED,
        contract_version: MATCH_RESULT_CONTRACT_VERSION,
      },
    ],
  };
}

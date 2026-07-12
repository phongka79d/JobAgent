import { describe, expect, it } from "vitest";

import { sampleMatchWire } from "./components/matchFixtures";
import {
  matchResultsToStructuredPayload,
  parseMatchResultsCardPayload,
  parseSavedJobCardPayload,
  safePublicSourceUrl,
} from "./contracts";

const JOB_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

describe("parseSavedJobCardPayload", () => {
  it("parses a valid backend saved_job payload", () => {
    const card = parseSavedJobCardPayload({
      kind: "saved_job",
      job_id: JOB_ID,
      title: "Engineer",
      company: "Acme",
      location: "NYC",
      work_mode: "hybrid",
      employment_type: "full_time",
      jd_quality: "partial",
      quality_reasons_preview: ["missing salary"],
      processing_result: "processed",
      duplicate_outcome: "none",
      graph_sync_status: "pending",
      source_url: "https://example.com/j",
    });
    expect(card).not.toBeNull();
    expect(card?.jobId).toBe(JOB_ID);
    expect(card?.title).toBe("Engineer");
    expect(card?.qualityReasonsPreview).toEqual(["missing salary"]);
    expect(card?.sourceUrl).toBe("https://example.com/j");
  });

  it("fails closed on wrong kind or missing job id", () => {
    expect(parseSavedJobCardPayload({ kind: "other", job_id: JOB_ID })).toBeNull();
    expect(
      parseSavedJobCardPayload({
        kind: "saved_job",
        processing_result: "processed",
        duplicate_outcome: "none",
        graph_sync_status: "pending",
      }),
    ).toBeNull();
  });

  it("drops unsafe source URLs and rejects non-uuid job ids", () => {
    const card = parseSavedJobCardPayload({
      kind: "saved_job",
      job_id: JOB_ID,
      processing_result: "processed",
      duplicate_outcome: "none",
      graph_sync_status: "synced",
      source_url: "http://localhost/secret",
    });
    expect(card?.sourceUrl).toBeNull();

    expect(
      parseSavedJobCardPayload({
        kind: "saved_job",
        job_id: "not-a-uuid",
        processing_result: "processed",
        duplicate_outcome: "none",
        graph_sync_status: "synced",
      }),
    ).toBeNull();
  });

  it("ignores raw/secret sentinel fields via extra-forbid fail-closed path", () => {
    // Extra keys are ignored by the loose parser; required fields still validate.
    const card = parseSavedJobCardPayload({
      kind: "saved_job",
      job_id: JOB_ID,
      processing_result: "processed",
      duplicate_outcome: "none",
      graph_sync_status: "pending",
      raw_content: "RAW_JD_BODY",
      api_key: "sk-secret",
    });
    expect(card).not.toBeNull();
    expect(JSON.stringify(card)).not.toMatch(/RAW_JD|sk-secret|raw_content|api_key/);
  });
});

describe("parseMatchResultsCardPayload", () => {
  it("parses a valid backend match_results payload", () => {
    const card = parseMatchResultsCardPayload(sampleMatchWire(JOB_ID));
    expect(card).not.toBeNull();
    expect(card?.kind).toBe("match_results");
    expect(card?.count).toBe(1);
    expect(card?.results[0]?.jobId).toBe(JOB_ID);
    expect(card?.results[0]?.title).toBe("Backend Engineer");
    expect(card?.results[0]?.finalScore).toBe(0.85);
    expect(card?.results[0]?.matchedRequiredSkills[0]?.displayName).toBe(
      "Python",
    );
    expect(card?.results[0]?.relatedSkills[0]?.matchKind).toBe(
      "verified_related",
    );
    expect(card?.results[0]?.sourceUrl).toBe(
      "https://example.com/jobs/backend",
    );
  });

  it("round-trips through structured payload serializer", () => {
    const card = parseMatchResultsCardPayload(sampleMatchWire(JOB_ID));
    expect(card).not.toBeNull();
    const wire = matchResultsToStructuredPayload(card!);
    const again = parseMatchResultsCardPayload(wire);
    expect(again).toEqual(card);
  });

  it("fails closed on wrong kind, count mismatch, oversized, incomplete components", () => {
    expect(parseMatchResultsCardPayload({ kind: "saved_job" })).toBeNull();
    expect(
      parseMatchResultsCardPayload({
        kind: "match_results",
        contract_version: "match_result_v1",
        seed_config_version: "hybrid_seed_v1",
        count: 2,
        results: [],
      }),
    ).toBeNull();

    const oversized = sampleMatchWire(JOB_ID);
    oversized.count = 11;
    oversized.results = Array.from({ length: 11 }, (_, i) => {
      const id = `aaaaaaaa-bbbb-4ccc-8ddd-${i.toString().padStart(12, "0")}`;
      return (sampleMatchWire(id).results as unknown[])[0];
    });
    expect(parseMatchResultsCardPayload(oversized)).toBeNull();

    const incomplete = sampleMatchWire(JOB_ID);
    const results = incomplete.results as Record<string, unknown>[];
    results[0] = {
      ...results[0],
      components: [{ name: "semantic_similarity", available: true, value: 1, effective_weight: 1 }],
    };
    expect(parseMatchResultsCardPayload(incomplete)).toBeNull();
  });

  it("drops unsafe URLs and rejects provisional skill kinds", () => {
    const wire = sampleMatchWire(JOB_ID);
    const results = wire.results as Record<string, unknown>[];
    results[0] = {
      ...results[0],
      source_url: "http://127.0.0.1/secret",
    };
    const card = parseMatchResultsCardPayload(wire);
    expect(card?.results[0]?.sourceUrl).toBeNull();

    const provisional = sampleMatchWire(JOB_ID);
    const pResults = provisional.results as Record<string, unknown>[];
    pResults[0] = {
      ...pResults[0],
      related_skills: [
        {
          canonical_key: "x",
          display_name: "X",
          match_kind: "provisional",
          strength: 0.5,
          related_path: ["a", "b"],
        },
      ],
    };
    expect(parseMatchResultsCardPayload(provisional)).toBeNull();
  });

  it("never surfaces raw sentinels on the typed card", () => {
    const wire = sampleMatchWire(JOB_ID);
    wire.raw_content = "RAW_JD_BODY";
    wire.api_key = "sk-secret";
    const card = parseMatchResultsCardPayload(wire);
    expect(card).not.toBeNull();
    expect(JSON.stringify(card)).not.toMatch(
      /RAW_JD|sk-secret|raw_content|api_key/,
    );
  });
});

describe("safePublicSourceUrl", () => {
  it("accepts public https and rejects private hosts", () => {
    expect(safePublicSourceUrl("https://example.com/j")).toBe(
      "https://example.com/j",
    );
    expect(safePublicSourceUrl("http://localhost/x")).toBeNull();
    expect(safePublicSourceUrl("not-a-url")).toBeNull();
  });
});

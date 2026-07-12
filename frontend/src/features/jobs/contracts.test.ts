import { describe, expect, it } from "vitest";

import { parseSavedJobCardPayload } from "./contracts";

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

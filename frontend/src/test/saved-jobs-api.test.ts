/**
 * Saved-JD typed transport and strict parser tests (Plan 10 / 05A).
 */
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  asSavedJobErrorCode,
  deleteSavedJob,
  evaluateSavedJob,
  fetchSavedJobDetail,
  fetchSavedJobs,
  isRetryableSavedJobDeleteError,
  SAVED_JOB_DELETE_RETRY_SUMMARY,
  SAVED_JOB_ERROR_CODES,
  saveAndEvaluateJob,
  toSavedJobActionError,
} from '../features/jobs/api';
import {
  parseEvaluateJobResponse,
  parseJobEvaluationView,
  parseJobPostExtraction,
  parseSaveAndEvaluateResponse,
  parseSavedJobDetail,
  parseSavedJobListItem,
  parseSavedJobListPage,
  selectSafeRemainingJobId,
} from '../features/jobs/types';

const JOB_A = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const JOB_B = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const EVAL_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const MSG_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';
const TS = '2024-08-01T12:00:00.000Z';

function matchResultPayload(jobId: string, score = 0.81) {
  return {
    job_id: jobId,
    title: 'Backend Engineer',
    company: 'Acme',
    location: 'Berlin',
    work_mode: 'hybrid',
    source_url: null,
    final_score: score,
    quality_multiplier: 1.0,
    components: {
      semantic_similarity: score,
      skill_score: null,
      seniority_score: null,
      experience_score: null,
      location_score: null,
      work_mode_score: null,
    },
    effective_weights: {semantic_similarity: 1.0},
    matched_required_skills: [],
    matched_preferred_skills: [],
    related_skills: [],
    missing_required_skills: [],
    summary: 'Solid fit',
  };
}

function listItemPayload(
  id: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    id,
    title: 'Backend Engineer',
    company: 'Acme',
    processing_status: 'processed',
    jd_quality: 'full',
    source_type: 'text',
    source_url: null,
    created_at: TS,
    updated_at: TS,
    evaluation_state: 'none',
    latest_score: null,
    ...overrides,
  };
}

function evaluationViewPayload(jobId: string, score = 0.81) {
  return {
    id: EVAL_ID,
    job_id: jobId,
    evaluation_state: 'current',
    evaluation_context_hash: 'ctx-hash-opaque-1',
    result: matchResultPayload(jobId, score),
    created_at: TS,
    updated_at: TS,
  };
}

function extractionPayload() {
  return {
    title: 'Backend Engineer',
    company: 'Acme',
    summary: 'Build APIs.',
    responsibilities: ['Design services'],
    required_skills: [
      {
        skill: {
          canonical_key: 'python',
          display_name: 'Python',
          aliases: ['python3'],
          category: 'language',
        },
        confidence: 0.91,
        evidence: ['Required: Python 3+'],
      },
    ],
    preferred_skills: [],
    seniority: 'mid',
    min_experience_years: 3.0,
    max_experience_years: 5.0,
    location: 'Berlin',
    work_mode: 'hybrid',
    extraction_confidence: 0.85,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('saved-JD strict parsers', () => {
  it('parses list page and rejects forbidden / extra fields', () => {
    const page = parseSavedJobListPage({
      items: [listItemPayload(JOB_A, {evaluation_state: 'stale', latest_score: 0.42})],
      next_cursor: null,
    });
    expect(page.items).toHaveLength(1);
    expect(page.items[0]!.evaluation_state).toBe('stale');
    expect(page.items[0]!.latest_score).toBe(0.42);

    expect(() =>
      parseSavedJobListItem({
        ...listItemPayload(JOB_A),
        raw_content: 'secret jd body',
      }),
    ).toThrow(/extra keys|raw_content/);

    expect(() =>
      parseSavedJobListItem({
        ...listItemPayload(JOB_A),
        embedding: [0.1, 0.2],
      }),
    ).toThrow(/extra keys|embedding/);

    expect(() =>
      parseSavedJobListItem({
        ...listItemPayload(JOB_A),
        evaluation_state: 'historical',
      }),
    ).toThrow(/evaluation_state/);

    expect(() =>
      parseSavedJobListPage({
        items: [listItemPayload(JOB_A)],
        next_cursor: null,
        provider_trace: {},
      }),
    ).toThrow(/extra keys/);
  });

  it('parses detail with extraction and MatchResult evaluation', () => {
    const detail = parseSavedJobDetail({
      compact: listItemPayload(JOB_A, {
        evaluation_state: 'current',
        latest_score: 0.81,
      }),
      extraction: extractionPayload(),
      raw_content: 'Full JD text',
      latest_evaluation: evaluationViewPayload(JOB_A),
    });
    expect(detail.raw_content).toBe('Full JD text');
    expect(detail.extraction?.summary).toBe('Build APIs.');
    expect(detail.latest_evaluation?.result.finalScore).toBe(0.81);
    expect(detail.latest_evaluation?.result.jobId).toBe(JOB_A);

    expect(() =>
      parseSavedJobDetail({
        compact: listItemPayload(JOB_A),
        extraction: extractionPayload(),
        raw_content: 'x',
        latest_evaluation: null,
        storage_path: '/secret',
      }),
    ).toThrow(/extra keys|storage_path/);

    expect(() =>
      parseJobPostExtraction({
        ...extractionPayload(),
        jd_quality: 'full',
      }),
    ).toThrow(/extra keys/);
  });

  it('accepts empty and whitespace extraction summaries while remaining strict', () => {
    const emptySummary = parseJobPostExtraction({
      ...extractionPayload(),
      summary: '',
    });
    expect(emptySummary.summary).toBe('');
    expect(emptySummary.title).toBe('Backend Engineer');
    expect(emptySummary.seniority).toBe('mid');

    const whitespaceSummary = parseJobPostExtraction({
      ...extractionPayload(),
      summary: '   \t',
    });
    expect(whitespaceSummary.summary).toBe('   \t');

    expect(() =>
      parseJobPostExtraction({
        ...extractionPayload(),
        summary: null,
      }),
    ).toThrow(/extraction\.summary must be a string/);

    expect(() =>
      parseJobPostExtraction({
        ...extractionPayload(),
        summary: 42,
      }),
    ).toThrow(/extraction\.summary must be a string/);

    const missingSummary = {...extractionPayload()} as Record<string, unknown>;
    delete missingSummary.summary;
    expect(() => parseJobPostExtraction(missingSummary)).toThrow(
      /missing required key summary/,
    );

    expect(() =>
      parseJobPostExtraction({
        ...extractionPayload(),
        extra_field: true,
      }),
    ).toThrow(/extra keys/);

    const detail = parseSavedJobDetail({
      compact: listItemPayload(JOB_A, {
        processing_status: 'processed',
        jd_quality: 'unscorable',
        evaluation_state: 'none',
      }),
      extraction: {...extractionPayload(), summary: ''},
      raw_content: 'contact only',
      latest_evaluation: null,
    });
    expect(detail.extraction?.summary).toBe('');
    expect(detail.compact.jd_quality).toBe('unscorable');
  });

  it('rejects malformed evaluation.result via MatchResult owner', () => {
    expect(() =>
      parseJobEvaluationView({
        ...evaluationViewPayload(JOB_A),
        result: {
          ...matchResultPayload(JOB_A),
          extra_score: 1,
        },
      }),
    ).toThrow(/MatchResult/);

    expect(() =>
      parseJobEvaluationView({
        ...evaluationViewPayload(JOB_A),
        result: {
          ...matchResultPayload(JOB_A),
          summary: '',
        },
      }),
    ).toThrow(/MatchResult/);
  });

  it('parses evaluate and save-and-evaluate outcomes strictly', () => {
    const evaluate = parseEvaluateJobResponse({
      outcome: 'created',
      job: listItemPayload(JOB_A, {
        evaluation_state: 'current',
        latest_score: 0.9,
      }),
      evaluation: evaluationViewPayload(JOB_A, 0.9),
    });
    expect(evaluate.outcome).toBe('created');

    const saveOk = parseSaveAndEvaluateResponse({
      ingest_outcome: 'created',
      job: listItemPayload(JOB_A, {
        evaluation_state: 'current',
        latest_score: 0.8,
      }),
      evaluation_outcome: 'created',
      evaluation: evaluationViewPayload(JOB_A, 0.8),
      code: null,
    });
    expect(saveOk.evaluation_outcome).toBe('created');

    const unavailable = parseSaveAndEvaluateResponse({
      ingest_outcome: 'existing',
      job: listItemPayload(JOB_A, {
        processing_status: 'failed',
        jd_quality: null,
        evaluation_state: 'none',
        latest_score: null,
      }),
      evaluation_outcome: 'unavailable',
      evaluation: null,
      code: 'JOB_NOT_SCORABLE',
    });
    expect(unavailable.code).toBe('JOB_NOT_SCORABLE');

    expect(() =>
      parseSaveAndEvaluateResponse({
        ingest_outcome: 'created',
        job: listItemPayload(JOB_A),
        evaluation_outcome: 'unavailable',
        evaluation: evaluationViewPayload(JOB_A),
        code: 'X',
      }),
    ).toThrow(/unavailable/);

    expect(() =>
      parseEvaluateJobResponse({
        outcome: 'failed',
        job: listItemPayload(JOB_A),
        evaluation: evaluationViewPayload(JOB_A),
      }),
    ).toThrow(/outcome/);
  });

  it('selects a deterministic remaining job after deletion', () => {
    const items = [{id: JOB_A}, {id: JOB_B}, {id: 'cccc'}];
    expect(selectSafeRemainingJobId(items, JOB_A, JOB_A)).toBe(JOB_B);
    expect(selectSafeRemainingJobId(items, JOB_A, JOB_B)).toBe(JOB_B);
    expect(selectSafeRemainingJobId(items, JOB_B, JOB_B)).toBe(JOB_A);
    expect(selectSafeRemainingJobId([{id: JOB_A}], JOB_A, JOB_A)).toBeNull();
  });
});

describe('saved-JD transport', () => {
  it('maps known codes and retryable delete summary', () => {
    for (const code of Object.values(SAVED_JOB_ERROR_CODES)) {
      expect(asSavedJobErrorCode(code)).toBe(code);
    }
    expect(asSavedJobErrorCode('UNKNOWN')).toBeNull();
    expect(
      isRetryableSavedJobDeleteError(
        SAVED_JOB_ERROR_CODES.JOB_DELETE_GRAPH_FAILED,
      ),
    ).toBe(true);
    expect(
      isRetryableSavedJobDeleteError(SAVED_JOB_ERROR_CODES.JOB_NOT_FOUND),
    ).toBe(false);
    const partial = toSavedJobActionError({
      code: SAVED_JOB_ERROR_CODES.JOB_DELETE_GRAPH_FAILED,
      summary: 'internal leak',
    });
    expect(partial.retryable).toBe(true);
    expect(partial.summary).toBe(SAVED_JOB_DELETE_RETRY_SUMMARY);
  });

  it('fetches list/detail and rejects smuggled forbidden error fields', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    const listBody = {
      items: [listItemPayload(JOB_A)],
      next_cursor: null,
    };
    const detailBody = {
      compact: listItemPayload(JOB_A, {
        evaluation_state: 'current',
        latest_score: 0.81,
      }),
      extraction: extractionPayload(),
      raw_content: 'JD',
      latest_evaluation: evaluationViewPayload(JOB_A),
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(listBody), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(detailBody), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: 'X',
              summary: 'y',
              storage_path: '/secret',
            },
          }),
          {status: 500, headers: {'Content-Type': 'application/json'}},
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    try {
      const page = await fetchSavedJobs({limit: 10});
      expect(page.items[0]!.id).toBe(JOB_A);
      expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
        'http://api.test/api/jobs?limit=10',
      );

      const detail = await fetchSavedJobDetail(JOB_A);
      expect(detail.latest_evaluation?.result.finalScore).toBe(0.81);
      expect(String(fetchMock.mock.calls[1]?.[0])).toBe(
        `http://api.test/api/jobs/${JOB_A}`,
      );

      await expect(fetchSavedJobs()).rejects.toMatchObject({
        code: 'FORBIDDEN_FIELD',
      });
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });

  it('evaluate / save-and-evaluate / delete transport contracts', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    const evaluateBody = {
      outcome: 'reused',
      job: listItemPayload(JOB_A, {
        evaluation_state: 'current',
        latest_score: 0.7,
      }),
      evaluation: evaluationViewPayload(JOB_A, 0.7),
    };
    const saveBody = {
      ingest_outcome: 'existing',
      job: listItemPayload(JOB_B, {
        evaluation_state: 'current',
        latest_score: 0.5,
      }),
      evaluation_outcome: 'reused',
      evaluation: evaluationViewPayload(JOB_B, 0.5),
      code: null,
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(evaluateBody), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(saveBody), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }),
      )
      .mockResolvedValueOnce(new Response(null, {status: 204}))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: SAVED_JOB_ERROR_CODES.JOB_DELETE_GRAPH_FAILED,
              summary: 'graph failed',
            },
          }),
          {status: 409, headers: {'Content-Type': 'application/json'}},
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              code: SAVED_JOB_ERROR_CODES.JOB_NOT_FOUND,
              summary: 'missing',
            },
          }),
          {status: 404, headers: {'Content-Type': 'application/json'}},
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    try {
      const evaluated = await evaluateSavedJob(JOB_A);
      expect(evaluated.outcome).toBe('reused');
      expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({method: 'POST'});
      expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
        `http://api.test/api/jobs/${JOB_A}/evaluate`,
      );

      const saved = await saveAndEvaluateJob(MSG_ID);
      expect(saved.ingest_outcome).toBe('existing');
      expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
        source_message_id: MSG_ID,
      });

      await expect(deleteSavedJob(JOB_A)).resolves.toBeUndefined();
      expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({method: 'DELETE'});

      await expect(deleteSavedJob(JOB_A)).rejects.toMatchObject({
        code: SAVED_JOB_ERROR_CODES.JOB_DELETE_GRAPH_FAILED,
        summary: SAVED_JOB_DELETE_RETRY_SUMMARY,
      });
      await expect(deleteSavedJob(JOB_A)).rejects.toMatchObject({
        code: SAVED_JOB_ERROR_CODES.JOB_NOT_FOUND,
      });
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

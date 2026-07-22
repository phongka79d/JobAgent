/**
 * Saved-JD sidebar-local state: request order, cache, actions, selection (05A).
 */
import {act, renderHook} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {ChatApiError} from '../lib/api/chat';
import {
  SAVED_JOB_DELETE_RETRY_SUMMARY,
  SAVED_JOB_ERROR_CODES,
} from '../features/jobs/api';
import {
  initialSavedJobsState,
  savedJobsReducer,
  useSavedJobsState,
} from '../features/jobs/savedJobsState';
import type {
  EvaluateJobResponse,
  ReextractJobResponse,
  SavedJobDetail,
  SavedJobListItem,
  SavedJobListPage,
  SelectedJobSkillMap,
} from '../features/jobs/types';
import {REEXTRACT_GRAPH_FAILURE_CODE} from '../features/jobs/types';

const JOB_A = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const JOB_B = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const JOB_C = 'cccccccc-dddd-4eee-8fff-000000000000';
const EVAL_ID = '11111111-2222-4333-8444-555555555555';
const TS = '2024-08-01T12:00:00.000Z';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return {promise, resolve};
}

function listItem(
  id: string,
  overrides: Partial<SavedJobListItem> = {},
): SavedJobListItem {
  return {
    id,
    title: `Title ${id.slice(0, 4)}`,
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

function listPage(items: SavedJobListItem[]): SavedJobListPage {
  return {items, next_cursor: null};
}

function matchResult(jobId: string, score: number) {
  return {
    jobId,
    title: 'Backend Engineer',
    company: 'Acme',
    location: 'Berlin',
    workMode: 'hybrid' as const,
    sourceUrl: null,
    finalScore: score,
    qualityMultiplier: 1,
    components: {
      semanticSimilarity: score,
      skillScore: null,
      seniorityScore: null,
      experienceScore: null,
      locationScore: null,
      workModeScore: null,
    },
    effectiveWeights: [{key: 'semantic_similarity' as const, weight: 1}],
    matchedRequiredSkills: [],
    matchedPreferredSkills: [],
    relatedSkills: [],
    missingRequiredSkills: [],
    summary: 'ok',
  };
}

function evaluateResponse(
  jobId: string,
  score: number,
): EvaluateJobResponse {
  return {
    outcome: 'created',
    job: listItem(jobId, {
      evaluation_state: 'current',
      latest_score: score,
    }),
    evaluation: {
      id: EVAL_ID,
      job_id: jobId,
      evaluation_state: 'current',
      evaluation_context_hash: 'ctx-1',
      result: matchResult(jobId, score),
      created_at: TS,
      updated_at: TS,
    },
  };
}

function detailFor(jobId: string): SavedJobDetail {
  return {
    compact: listItem(jobId, {
      evaluation_state: 'stale',
      latest_score: 0.4,
    }),
    extraction: {
      title: 'Old title',
      company: 'Acme',
      summary: 'Old extraction',
      responsibilities: ['Old resp'],
      required_skills: [],
      preferred_skills: [],
      seniority: 'mid',
      min_experience_years: 2,
      max_experience_years: 4,
      location: 'Berlin',
      work_mode: 'hybrid',
      extraction_confidence: 0.5,
    },
    raw_content: 'raw',
    latest_evaluation: {
      id: EVAL_ID,
      job_id: jobId,
      evaluation_state: 'stale',
      evaluation_context_hash: 'old',
      result: matchResult(jobId, 0.4),
      created_at: TS,
      updated_at: TS,
    },
  };
}

function reextractResponse(
  jobId: string,
  overrides: Partial<ReextractJobResponse> = {},
): ReextractJobResponse {
  return {
    outcome: 'updated',
    job: listItem(jobId, {
      evaluation_state: 'stale',
      latest_score: 0.4,
      title: 'Refreshed title',
    }),
    sync_ok: true,
    code: null,
    rebuild_instruction: null,
    ...overrides,
  };
}

function skillMapFor(
  jobId: string,
  displayName = 'Audience Research',
): SelectedJobSkillMap {
  return {
    status: 'ready',
    code: null,
    summary: 'Selected map is ready.',
    rebuild_instruction: null,
    candidate: {
      id: 'active',
      attachment_id: EVAL_ID,
      current_title: 'Coordinator',
      revision: TS,
    },
    job: {
      id: jobId,
      title: `Title ${jobId.slice(0, 4)}`,
      company: 'Acme',
      revision: TS,
    },
    items: [
      {
        match_type: 'candidate_only',
        requirement: 'none',
        strength: 0,
        candidate_skill: {
          canonical_key: 'audience_research',
          display_name: displayName,
          confidence: 0.9,
          evidence: [`Evidence for ${displayName}`],
        },
        job_skill: null,
        relationship: null,
      },
    ],
    counts: {
      direct: 0,
      related: 0,
      missing_required: 0,
      missing_preferred: 0,
      candidate_only: 1,
    },
    checked_at: TS,
  };
}

describe('selected skill-map cache ownership', () => {
  it('keeps request ordering independent per Job and retains safe cached data', async () => {
    const initial = deferred<SelectedJobSkillMap>();
    const refresh = deferred<SelectedJobSkillMap>();
    const other = deferred<SelectedJobSkillMap>();
    const fetchSelectedJobSkillMap = vi
      .fn()
      .mockReturnValueOnce(initial.promise)
      .mockReturnValueOnce(refresh.promise)
      .mockReturnValueOnce(other.promise)
      .mockRejectedValueOnce(new ChatApiError(500, 'DOWN', 'map down'));
    const {result} = renderHook(() =>
      useSavedJobsState({api: {fetchSelectedJobSkillMap}}),
    );
    let initialLoad!: Promise<void>;
    let forced!: Promise<void>;
    let otherLoad!: Promise<void>;

    act(() => {
      initialLoad = result.current.loadSkillMap(JOB_A);
      forced = result.current.loadSkillMap(JOB_A, {force: true});
      otherLoad = result.current.loadSkillMap(JOB_B);
    });
    await act(async () => {
      refresh.resolve(skillMapFor(JOB_A, 'Newer label'));
      other.resolve(skillMapFor(JOB_B, 'Other label'));
      await Promise.all([forced, otherLoad]);
    });
    await act(async () => {
      initial.resolve(skillMapFor(JOB_A, 'Older label'));
      await initialLoad;
    });

    expect(
      result.current.state.skillMaps[JOB_A]?.data?.items[0]?.candidate_skill
        ?.display_name,
    ).toBe('Newer label');
    expect(
      result.current.state.skillMaps[JOB_B]?.data?.items[0]?.candidate_skill
        ?.display_name,
    ).toBe('Other label');

    await act(async () => {
      await result.current.loadSkillMap(JOB_A, {force: true});
    });
    expect(result.current.state.skillMaps[JOB_A]?.phase).toBe('error');
    expect(
      result.current.state.skillMaps[JOB_A]?.data?.items[0]?.candidate_skill
        ?.display_name,
    ).toBe('Newer label');
  });

  it('invalidates map caches for active-CV, re-extract, and delete without evaluating', async () => {
    const fetchSelectedJobSkillMap = vi
      .fn()
      .mockResolvedValue(skillMapFor(JOB_A));
    const reextractSavedJob = vi.fn().mockResolvedValue(reextractResponse(JOB_A));
    const fetchSavedJobDetail = vi.fn().mockResolvedValue(detailFor(JOB_A));
    const deleteSavedJob = vi.fn().mockResolvedValue(undefined);
    const evaluateSavedJob = vi.fn();
    const {result} = renderHook(() =>
      useSavedJobsState({
        api: {
          fetchSelectedJobSkillMap,
          reextractSavedJob,
          fetchSavedJobDetail,
          deleteSavedJob,
          evaluateSavedJob,
        },
      }),
    );

    await act(async () => {
      await result.current.loadSkillMap(JOB_A);
    });
    act(() => {
      result.current.selectJob(JOB_A);
      result.current.invalidateCurrentness();
    });
    expect(result.current.state.skillMaps[JOB_A]).toMatchObject({
      phase: 'loading',
      loaded: false,
    });
    expect(result.current.state.skillMaps[JOB_A]?.data).not.toBeNull();

    await act(async () => {
      await result.current.loadSkillMap(JOB_A, {force: true});
      await result.current.confirmReextract(JOB_A);
    });
    expect(result.current.state.skillMaps[JOB_A]).toMatchObject({
      phase: 'loading',
      loaded: false,
    });

    await act(async () => {
      await result.current.confirmDelete(JOB_A);
    });
    expect(result.current.state.skillMaps[JOB_A]).toBeUndefined();
    expect(evaluateSavedJob).not.toHaveBeenCalled();
  });

  it('ignores an in-flight map response after currentness invalidation', async () => {
    const pending = deferred<SelectedJobSkillMap>();
    const fetchSelectedJobSkillMap = vi.fn().mockReturnValue(pending.promise);
    const {result} = renderHook(() =>
      useSavedJobsState({api: {fetchSelectedJobSkillMap}}),
    );
    let load!: Promise<void>;

    act(() => {
      load = result.current.loadSkillMap(JOB_A);
    });
    act(() => {
      result.current.invalidateCurrentness();
    });
    await act(async () => {
      pending.resolve(skillMapFor(JOB_A, 'Outdated label'));
      await load;
    });

    expect(result.current.state.skillMaps[JOB_A]).toMatchObject({
      phase: 'loading',
      data: null,
      loaded: false,
    });
  });

  it('ignores an in-flight map response after successful re-extraction', async () => {
    const pending = deferred<SelectedJobSkillMap>();
    const fetchSelectedJobSkillMap = vi.fn().mockReturnValue(pending.promise);
    const reextractSavedJob = vi.fn().mockResolvedValue(reextractResponse(JOB_A));
    const fetchSavedJobDetail = vi.fn().mockResolvedValue(detailFor(JOB_A));
    const {result} = renderHook(() =>
      useSavedJobsState({
        api: {
          fetchSelectedJobSkillMap,
          reextractSavedJob,
          fetchSavedJobDetail,
        },
      }),
    );
    let load!: Promise<void>;

    act(() => {
      load = result.current.loadSkillMap(JOB_A);
    });
    await act(async () => {
      await result.current.confirmReextract(JOB_A);
    });
    await act(async () => {
      pending.resolve(skillMapFor(JOB_A, 'Outdated label'));
      await load;
    });

    expect(result.current.state.skillMaps[JOB_A]).toMatchObject({
      phase: 'loading',
      data: null,
      loaded: false,
    });
  });

  it('does not recreate a deleted Job map from an older in-flight response', async () => {
    const pending = deferred<SelectedJobSkillMap>();
    const fetchSelectedJobSkillMap = vi.fn().mockReturnValue(pending.promise);
    const deleteSavedJob = vi.fn().mockResolvedValue(undefined);
    const {result} = renderHook(() =>
      useSavedJobsState({api: {fetchSelectedJobSkillMap, deleteSavedJob}}),
    );
    let load!: Promise<void>;

    act(() => {
      load = result.current.loadSkillMap(JOB_A);
    });
    await act(async () => {
      await result.current.confirmDelete(JOB_A);
    });
    await act(async () => {
      pending.resolve(skillMapFor(JOB_A, 'Deleted Job label'));
      await load;
    });

    expect(result.current.state.skillMaps[JOB_A]).toBeUndefined();
  });
});

describe('saved-JD request ordering and stale-on-error', () => {
  it('ignores an older list request after a forced refresh succeeds', async () => {
    const initial = deferred<SavedJobListPage>();
    const refresh = deferred<SavedJobListPage>();
    const fetchSavedJobs = vi
      .fn()
      .mockReturnValueOnce(initial.promise)
      .mockReturnValueOnce(refresh.promise);
    const {result} = renderHook(() =>
      useSavedJobsState({api: {fetchSavedJobs}}),
    );
    let initialLoad!: Promise<void>;
    let forcedRefresh!: Promise<void>;

    act(() => {
      initialLoad = result.current.loadList();
      forcedRefresh = result.current.loadList({}, {force: true});
    });

    const refreshed = listPage([
      listItem(JOB_A, {title: 'newer'}),
    ]);
    await act(async () => {
      refresh.resolve(refreshed);
      await forcedRefresh;
    });

    await act(async () => {
      initial.resolve(listPage([listItem(JOB_A, {title: 'older'})]));
      await initialLoad;
    });

    expect(result.current.state.list.data?.items[0]?.title).toBe('newer');
  });

  it('keeps request ordering independent per detail cache key', async () => {
    const initial = deferred<SavedJobDetail>();
    const refresh = deferred<SavedJobDetail>();
    const other = deferred<SavedJobDetail>();
    const fetchSavedJobDetail = vi
      .fn()
      .mockReturnValueOnce(initial.promise)
      .mockReturnValueOnce(refresh.promise)
      .mockReturnValueOnce(other.promise);
    const {result} = renderHook(() =>
      useSavedJobsState({api: {fetchSavedJobDetail}}),
    );
    let initialLoad!: Promise<void>;
    let forced!: Promise<void>;
    let otherLoad!: Promise<void>;

    act(() => {
      initialLoad = result.current.loadDetail(JOB_A);
      forced = result.current.loadDetail(JOB_A, {force: true});
      otherLoad = result.current.loadDetail(JOB_B);
    });

    const refreshedDetail = detailFor(JOB_A);
    refreshedDetail.raw_content = 'newer raw';
    const otherDetail = detailFor(JOB_B);
    otherDetail.raw_content = 'other raw';
    await act(async () => {
      refresh.resolve(refreshedDetail);
      other.resolve(otherDetail);
      await Promise.all([forced, otherLoad]);
    });

    const older = detailFor(JOB_A);
    older.raw_content = 'older raw';
    await act(async () => {
      initial.resolve(older);
      await initialLoad;
    });

    expect(result.current.state.details[JOB_A]?.data?.raw_content).toBe(
      'newer raw',
    );
    expect(result.current.state.details[JOB_B]?.data?.raw_content).toBe(
      'other raw',
    );
  });

  it('preserves prior successful list/detail data after failed reloads', async () => {
    const fetchSavedJobs = vi
      .fn()
      .mockResolvedValueOnce(listPage([listItem(JOB_A)]))
      .mockRejectedValueOnce(new ChatApiError(500, 'DOWN', 'list down'));
    const fetchSavedJobDetail = vi
      .fn()
      .mockResolvedValueOnce(detailFor(JOB_A))
      .mockRejectedValueOnce(new ChatApiError(500, 'DOWN', 'detail down'));
    const {result} = renderHook(() =>
      useSavedJobsState({api: {fetchSavedJobs, fetchSavedJobDetail}}),
    );

    await act(async () => {
      await result.current.loadList();
      await result.current.loadDetail(JOB_A);
    });
    expect(result.current.state.list.phase).toBe('ready');
    expect(result.current.state.details[JOB_A]?.phase).toBe('ready');

    await act(async () => {
      await result.current.loadList({}, {force: true});
      await result.current.loadDetail(JOB_A, {force: true});
    });

    expect(result.current.state.list.phase).toBe('error');
    expect(result.current.state.list.data?.items[0]?.id).toBe(JOB_A);
    expect(result.current.state.list.loaded).toBe(true);
    expect(result.current.state.details[JOB_A]?.phase).toBe('error');
    expect(result.current.state.details[JOB_A]?.data?.raw_content).toBe('raw');
    expect(result.current.state.details[JOB_A]?.loaded).toBe(true);
  });
});

describe('saved-JD actions, invalidation, and selection', () => {
  it('prevents duplicate pending actions per job', () => {
    let state = initialSavedJobsState;
    state = savedJobsReducer(state, {
      type: 'action_begin',
      jobId: JOB_A,
      kind: 'evaluate',
    });
    expect(state.actions.pendingByJob[JOB_A]).toBe('evaluate');
    const dup = savedJobsReducer(state, {
      type: 'action_begin',
      jobId: JOB_A,
      kind: 'delete',
    });
    expect(dup.actions.pendingByJob[JOB_A]).toBe('evaluate');
    expect(dup).toBe(state);
  });

  it('evaluate success patches list/detail and bumps graph/chat only', () => {
    let state = initialSavedJobsState;
    state = savedJobsReducer(state, {
      type: 'list_success',
      data: listPage([
        listItem(JOB_A, {evaluation_state: 'stale', latest_score: 0.2}),
        listItem(JOB_B),
      ]),
    });
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_A,
      data: detailFor(JOB_A),
    });
    state = savedJobsReducer(state, {
      type: 'action_begin',
      jobId: JOB_A,
      kind: 'evaluate',
    });
    const priorGraph = state.externalInvalidation.graphGeneration;
    const priorChat = state.externalInvalidation.chatCardGeneration;
    const priorB = state.list.data?.items[1];

    state = savedJobsReducer(state, {
      type: 'evaluate_success',
      jobId: JOB_A,
      response: evaluateResponse(JOB_A, 0.95),
    });

    expect(state.list.data?.items[0]?.latest_score).toBe(0.95);
    expect(state.list.data?.items[0]?.evaluation_state).toBe('current');
    expect(state.list.data?.items[1]).toEqual(priorB);
    expect(state.details[JOB_A]?.data?.latest_evaluation?.result.finalScore).toBe(
      0.95,
    );
    expect(state.details[JOB_A]?.data?.raw_content).toBe('raw');
    expect(state.actions.pendingByJob[JOB_A]).toBeUndefined();
    expect(state.externalInvalidation.graphGeneration).toBe(priorGraph + 1);
    expect(state.externalInvalidation.chatCardGeneration).toBe(priorChat + 1);
    // No second observability architecture: only generations, not graph payload.
    expect('graph' in state).toBe(false);
  });

  it('delete success removes row, drops detail, selects safe remaining, invalidates', () => {
    let state = initialSavedJobsState;
    state = savedJobsReducer(state, {
      type: 'list_success',
      data: listPage([listItem(JOB_A), listItem(JOB_B), listItem(JOB_C)]),
    });
    state = savedJobsReducer(state, {type: 'select_job', jobId: JOB_A});
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_A,
      data: detailFor(JOB_A),
    });
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_B,
      data: detailFor(JOB_B),
    });
    state = savedJobsReducer(state, {
      type: 'action_begin',
      jobId: JOB_A,
      kind: 'delete',
    });

    state = savedJobsReducer(state, {type: 'delete_success', jobId: JOB_A});

    expect(state.list.data?.items.map((i) => i.id)).toEqual([JOB_B, JOB_C]);
    expect(state.selectedJobId).toBe(JOB_B);
    expect(state.details[JOB_A]).toBeUndefined();
    expect(state.details[JOB_B]?.data).toBeTruthy();
    expect(state.actions.pendingByJob[JOB_A]).toBeUndefined();
    expect(state.externalInvalidation.graphGeneration).toBe(1);
    expect(state.externalInvalidation.chatCardGeneration).toBe(1);
  });

  it('delete keeps non-deleted selection; last row yields null selection', () => {
    let state = initialSavedJobsState;
    state = savedJobsReducer(state, {
      type: 'list_success',
      data: listPage([listItem(JOB_A), listItem(JOB_B)]),
    });
    state = savedJobsReducer(state, {type: 'select_job', jobId: JOB_B});
    state = savedJobsReducer(state, {type: 'delete_success', jobId: JOB_A});
    expect(state.selectedJobId).toBe(JOB_B);

    state = savedJobsReducer(state, {type: 'delete_success', jobId: JOB_B});
    expect(state.selectedJobId).toBeNull();
    expect(state.list.phase).toBe('empty');
    expect(state.list.data?.items).toHaveLength(0);
  });

  it('retains list/selection on delete failure with retry guidance', async () => {
    const deleteSavedJob = vi.fn().mockRejectedValue(
      new ChatApiError(
        409,
        SAVED_JOB_ERROR_CODES.JOB_DELETE_GRAPH_FAILED,
        'graph failed',
      ),
    );
    const fetchSavedJobs = vi
      .fn()
      .mockResolvedValue(listPage([listItem(JOB_A), listItem(JOB_B)]));
    const {result} = renderHook(() =>
      useSavedJobsState({api: {deleteSavedJob, fetchSavedJobs}}),
    );
    await act(async () => {
      await result.current.loadList();
    });
    act(() => {
      result.current.selectJob(JOB_A);
    });
    const priorItems = result.current.state.list.data?.items;
    const priorSelection = result.current.state.selectedJobId;

    let outcome: 'success' | 'duplicate' | 'error' = 'success';
    await act(async () => {
      outcome = await result.current.confirmDelete(JOB_A);
    });

    expect(outcome).toBe('error');
    expect(result.current.state.list.data?.items).toEqual(priorItems);
    expect(result.current.state.selectedJobId).toBe(priorSelection);
    expect(result.current.state.actions.errorsByJob[JOB_A]?.summary).toBe(
      SAVED_JOB_DELETE_RETRY_SUMMARY,
    );
    expect(result.current.state.actions.pendingByJob[JOB_A]).toBeUndefined();
    expect(result.current.state.externalInvalidation.graphGeneration).toBe(0);
  });

  it('blocks duplicate evaluate and delete while pending', async () => {
    const gate = deferred<EvaluateJobResponse>();
    const evaluateSavedJob = vi.fn().mockReturnValue(gate.promise);
    const deleteGate = deferred<void>();
    const deleteSavedJob = vi.fn().mockReturnValue(deleteGate.promise);
    const {result} = renderHook(() =>
      useSavedJobsState({api: {evaluateSavedJob, deleteSavedJob}}),
    );

    let firstEval!: Promise<'success' | 'duplicate' | 'error'>;
    let secondEval!: Promise<'success' | 'duplicate' | 'error'>;
    act(() => {
      firstEval = result.current.evaluateJob(JOB_A);
      secondEval = result.current.evaluateJob(JOB_A);
    });
    expect(await secondEval).toBe('duplicate');
    await act(async () => {
      gate.resolve(evaluateResponse(JOB_A, 0.5));
      await firstEval;
    });
    expect(evaluateSavedJob).toHaveBeenCalledTimes(1);

    let firstDel!: Promise<'success' | 'duplicate' | 'error'>;
    let secondDel!: Promise<'success' | 'duplicate' | 'error'>;
    act(() => {
      firstDel = result.current.confirmDelete(JOB_B);
      secondDel = result.current.confirmDelete(JOB_B);
    });
    expect(await secondDel).toBe('duplicate');
    await act(async () => {
      deleteGate.resolve();
      await firstDel;
    });
    expect(deleteSavedJob).toHaveBeenCalledTimes(1);
  });

  it('evaluate hook success updates list row without clearing other jobs', async () => {
    const evaluateSavedJob = vi
      .fn()
      .mockResolvedValue(evaluateResponse(JOB_A, 0.88));
    const fetchSavedJobs = vi
      .fn()
      .mockResolvedValue(
        listPage([
          listItem(JOB_A, {evaluation_state: 'none', latest_score: null}),
          listItem(JOB_B),
        ]),
      );
    const {result} = renderHook(() =>
      useSavedJobsState({api: {evaluateSavedJob, fetchSavedJobs}}),
    );
    await act(async () => {
      await result.current.loadList();
    });
    let outcome: 'success' | 'duplicate' | 'error' = 'error';
    await act(async () => {
      outcome = await result.current.evaluateJob(JOB_A);
    });
    expect(outcome).toBe('success');
    expect(result.current.state.list.data?.items[0]?.latest_score).toBe(0.88);
    expect(result.current.state.list.data?.items[1]?.id).toBe(JOB_B);
    expect(result.current.state.externalInvalidation.graphGeneration).toBe(1);
  });

  it('invalidate_currentness preserves selection and safe data without evaluate', () => {
    let state = initialSavedJobsState;
    const currentCompact = listItem(JOB_A, {
      evaluation_state: 'current',
      latest_score: 0.9,
    });
    const selectedDetail: SavedJobDetail = {
      compact: currentCompact,
      extraction: null,
      raw_content: 'raw-a',
      latest_evaluation: {
        id: EVAL_ID,
        job_id: JOB_A,
        evaluation_state: 'current',
        evaluation_context_hash: 'ctx-1',
        result: matchResult(JOB_A, 0.9),
        created_at: TS,
        updated_at: TS,
      },
    };
    state = savedJobsReducer(state, {
      type: 'list_success',
      data: listPage([currentCompact, listItem(JOB_B)]),
    });
    state = savedJobsReducer(state, {type: 'select_job', jobId: JOB_A});
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_A,
      data: selectedDetail,
    });
    // Unselected detail stays cached but is not marked non-current.
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_B,
      data: detailFor(JOB_B),
    });
    const priorList = state.list.data;
    const priorSelectedDetail = state.details[JOB_A]?.data;
    const priorB = state.details[JOB_B];
    const priorGraph = state.externalInvalidation.graphGeneration;

    state = savedJobsReducer(state, {type: 'invalidate_currentness'});

    expect(state.selectedJobId).toBe(JOB_A);
    expect(state.list.loaded).toBe(false);
    expect(state.list.phase).toBe('loading');
    expect(state.list.data).toEqual(priorList);
    expect(state.list.data?.items[0]?.evaluation_state).toBe('current');
    expect(state.details[JOB_A]?.loaded).toBe(false);
    expect(state.details[JOB_A]?.phase).toBe('loading');
    expect(state.details[JOB_A]?.data).toEqual(priorSelectedDetail);
    expect(state.details[JOB_B]).toEqual(priorB);
    // No automatic evaluate and no external generation bump.
    expect(state.externalInvalidation.graphGeneration).toBe(priorGraph);
    expect(state.actions.pendingByJob[JOB_A]).toBeUndefined();
  });

  it('invalidateCurrentness forces open-tab list/detail GET; closed tab lazy refresh', async () => {
    const currentPage = listPage([
      listItem(JOB_A, {evaluation_state: 'current', latest_score: 0.91}),
    ]);
    const stalePage = listPage([
      listItem(JOB_A, {evaluation_state: 'stale', latest_score: 0.91}),
    ]);
    const currentDetail: SavedJobDetail = {
      compact: listItem(JOB_A, {
        evaluation_state: 'current',
        latest_score: 0.91,
      }),
      extraction: null,
      raw_content: 'raw',
      latest_evaluation: {
        id: EVAL_ID,
        job_id: JOB_A,
        evaluation_state: 'current',
        evaluation_context_hash: 'ctx-1',
        result: matchResult(JOB_A, 0.91),
        created_at: TS,
        updated_at: TS,
      },
    };
    const staleDetail: SavedJobDetail = {
      compact: listItem(JOB_A, {
        evaluation_state: 'stale',
        latest_score: 0.91,
      }),
      extraction: null,
      raw_content: 'raw',
      latest_evaluation: {
        id: EVAL_ID,
        job_id: JOB_A,
        evaluation_state: 'stale',
        evaluation_context_hash: 'ctx-old',
        result: matchResult(JOB_A, 0.91),
        created_at: TS,
        updated_at: TS,
      },
    };
    const fetchSavedJobs = vi
      .fn()
      .mockResolvedValueOnce(currentPage)
      .mockResolvedValueOnce(stalePage);
    const fetchSavedJobDetail = vi
      .fn()
      .mockResolvedValueOnce(currentDetail)
      .mockResolvedValueOnce(staleDetail);
    const evaluateSavedJob = vi.fn();
    const {result} = renderHook(() =>
      useSavedJobsState({
        api: {fetchSavedJobs, fetchSavedJobDetail, evaluateSavedJob},
      }),
    );

    await act(async () => {
      await result.current.loadList();
      await result.current.loadDetail(JOB_A);
    });
    act(() => {
      result.current.selectJob(JOB_A);
    });
    expect(result.current.state.list.data?.items[0]?.evaluation_state).toBe(
      'current',
    );
    expect(fetchSavedJobs).toHaveBeenCalledTimes(1);
    expect(fetchSavedJobDetail).toHaveBeenCalledTimes(1);

    // Closed-tab path: mark non-current but do not fetch until next use.
    act(() => {
      result.current.invalidateCurrentness();
    });
    expect(result.current.state.list.loaded).toBe(false);
    expect(result.current.state.details[JOB_A]?.loaded).toBe(false);
    expect(result.current.state.selectedJobId).toBe(JOB_A);
    expect(fetchSavedJobs).toHaveBeenCalledTimes(1);
    expect(fetchSavedJobDetail).toHaveBeenCalledTimes(1);
    expect(evaluateSavedJob).not.toHaveBeenCalled();

    // Open-tab / next-use path: force list + selected detail GET; server stale.
    await act(async () => {
      await result.current.loadList({}, {force: true});
      await result.current.loadDetail(JOB_A, {force: true});
    });
    expect(fetchSavedJobs).toHaveBeenCalledTimes(2);
    expect(fetchSavedJobDetail).toHaveBeenCalledTimes(2);
    expect(result.current.state.list.data?.items[0]?.evaluation_state).toBe(
      'stale',
    );
    expect(
      result.current.state.details[JOB_A]?.data?.compact.evaluation_state,
    ).toBe('stale');
    expect(evaluateSavedJob).not.toHaveBeenCalled();
  });

  it('reextract success patches compact row, never invents extraction, bumps graph', () => {
    let state = initialSavedJobsState;
    const priorDetail = detailFor(JOB_A);
    state = savedJobsReducer(state, {
      type: 'list_success',
      data: listPage([
        listItem(JOB_A, {
          evaluation_state: 'current',
          latest_score: 0.9,
          title: 'Old title',
        }),
        listItem(JOB_B),
      ]),
    });
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_A,
      data: priorDetail,
    });
    state = savedJobsReducer(state, {
      type: 'action_begin',
      jobId: JOB_A,
      kind: 'reextract',
    });
    const priorGraph = state.externalInvalidation.graphGeneration;
    const priorExtraction = state.details[JOB_A]?.data?.extraction;

    state = savedJobsReducer(state, {
      type: 'reextract_success',
      jobId: JOB_A,
      response: reextractResponse(JOB_A),
    });

    expect(state.list.data?.items[0]?.title).toBe('Refreshed title');
    expect(state.list.data?.items[0]?.evaluation_state).toBe('stale');
    expect(state.list.data?.items[1]?.id).toBe(JOB_B);
    // Prior extraction remains until force-refetch; never optimistically rewritten.
    expect(state.details[JOB_A]?.data?.extraction).toEqual(priorExtraction);
    expect(state.details[JOB_A]?.data?.compact.title).toBe('Refreshed title');
    expect(state.details[JOB_A]?.loaded).toBe(false);
    expect(state.details[JOB_A]?.phase).toBe('loading');
    expect(state.actions.pendingByJob[JOB_A]).toBeUndefined();
    expect(state.externalInvalidation.graphGeneration).toBe(priorGraph + 1);
    expect(state.actions.errorsByJob[JOB_A]).toBeUndefined();
  });

  it('reextract graph-warning success still refreshes and shows rebuild guidance', () => {
    let state = initialSavedJobsState;
    state = savedJobsReducer(state, {
      type: 'list_success',
      data: listPage([listItem(JOB_A, {evaluation_state: 'current'})]),
    });
    state = savedJobsReducer(state, {
      type: 'detail_success',
      jobId: JOB_A,
      data: detailFor(JOB_A),
    });
    state = savedJobsReducer(state, {
      type: 'action_begin',
      jobId: JOB_A,
      kind: 'reextract',
    });

    state = savedJobsReducer(state, {
      type: 'reextract_success',
      jobId: JOB_A,
      response: reextractResponse(JOB_A, {
        sync_ok: false,
        code: REEXTRACT_GRAPH_FAILURE_CODE,
        rebuild_instruction: 'Run local graph rebuild.',
      }),
    });

    expect(state.list.data?.items[0]?.title).toBe('Refreshed title');
    expect(state.details[JOB_A]?.loaded).toBe(false);
    expect(state.externalInvalidation.graphGeneration).toBe(1);
    expect(state.actions.errorsByJob[JOB_A]?.code).toBe(
      REEXTRACT_GRAPH_FAILURE_CODE,
    );
    expect(state.actions.errorsByJob[JOB_A]?.summary).toMatch(/rebuild/i);
  });

  it('reextract pre-commit failure preserves list/detail and shows safe summary only', async () => {
    const reextractSavedJob = vi.fn().mockRejectedValue(
      new ChatApiError(422, 'JD_SOURCE_NOT_RECOVERABLE', 'Source not recoverable'),
    );
    const evaluateSavedJob = vi.fn();
    const fetchSavedJobs = vi
      .fn()
      .mockResolvedValue(
        listPage([
          listItem(JOB_A, {
            evaluation_state: 'current',
            latest_score: 0.9,
            title: 'Stable',
          }),
        ]),
      );
    const fetchSavedJobDetail = vi.fn().mockResolvedValue(detailFor(JOB_A));
    const {result} = renderHook(() =>
      useSavedJobsState({
        api: {
          reextractSavedJob,
          evaluateSavedJob,
          fetchSavedJobs,
          fetchSavedJobDetail,
        },
      }),
    );

    await act(async () => {
      await result.current.loadList();
      await result.current.loadDetail(JOB_A);
    });
    const priorList = result.current.state.list.data;
    const priorDetail = result.current.state.details[JOB_A]?.data;
    const priorGraph = result.current.state.externalInvalidation.graphGeneration;

    let outcome: 'success' | 'duplicate' | 'error' = 'success';
    await act(async () => {
      outcome = await result.current.confirmReextract(JOB_A);
    });

    expect(outcome).toBe('error');
    expect(result.current.state.list.data).toEqual(priorList);
    expect(result.current.state.details[JOB_A]?.data).toEqual(priorDetail);
    expect(result.current.state.actions.errorsByJob[JOB_A]?.code).toBe(
      'JD_SOURCE_NOT_RECOVERABLE',
    );
    expect(result.current.state.actions.errorsByJob[JOB_A]?.summary).toBe(
      'Source not recoverable',
    );
    expect(result.current.state.actions.pendingByJob[JOB_A]).toBeUndefined();
    expect(result.current.state.externalInvalidation.graphGeneration).toBe(
      priorGraph,
    );
    expect(evaluateSavedJob).not.toHaveBeenCalled();
  });

  it('reextract hook success force-refetches detail and never calls evaluate', async () => {
    const reextractSavedJob = vi.fn().mockResolvedValue(
      reextractResponse(JOB_A, {
        job: listItem(JOB_A, {
          evaluation_state: 'stale',
          latest_score: 0.9,
          title: 'After reextract',
        }),
      }),
    );
    const evaluateSavedJob = vi.fn();
    const refreshedDetail: SavedJobDetail = {
      compact: listItem(JOB_A, {
        evaluation_state: 'stale',
        latest_score: 0.9,
        title: 'After reextract',
      }),
      extraction: {
        title: 'After reextract',
        company: 'Acme',
        summary: 'New extraction',
        responsibilities: ['New duty'],
        required_skills: [],
        preferred_skills: [],
        seniority: 'senior',
        min_experience_years: 5,
        max_experience_years: null,
        location: 'Remote',
        work_mode: 'remote',
        extraction_confidence: 0.95,
      },
      raw_content: 'raw',
      latest_evaluation: {
        id: EVAL_ID,
        job_id: JOB_A,
        evaluation_state: 'stale',
        evaluation_context_hash: 'old',
        result: matchResult(JOB_A, 0.9),
        created_at: TS,
        updated_at: TS,
      },
    };
    const fetchSavedJobs = vi
      .fn()
      .mockResolvedValue(
        listPage([
          listItem(JOB_A, {
            evaluation_state: 'current',
            latest_score: 0.9,
            title: 'Before',
          }),
        ]),
      );
    const fetchSavedJobDetail = vi
      .fn()
      .mockResolvedValueOnce(detailFor(JOB_A))
      .mockResolvedValueOnce(refreshedDetail);
    const {result} = renderHook(() =>
      useSavedJobsState({
        api: {
          reextractSavedJob,
          evaluateSavedJob,
          fetchSavedJobs,
          fetchSavedJobDetail,
        },
      }),
    );

    await act(async () => {
      await result.current.loadList();
      await result.current.loadDetail(JOB_A);
    });
    expect(result.current.state.details[JOB_A]?.data?.extraction?.summary).toBe(
      'Old extraction',
    );

    let outcome: 'success' | 'duplicate' | 'error' = 'error';
    await act(async () => {
      outcome = await result.current.confirmReextract(JOB_A);
    });

    expect(outcome).toBe('success');
    expect(reextractSavedJob).toHaveBeenCalledTimes(1);
    expect(fetchSavedJobDetail).toHaveBeenCalledTimes(2);
    expect(result.current.state.list.data?.items[0]?.title).toBe(
      'After reextract',
    );
    expect(result.current.state.list.data?.items[0]?.evaluation_state).toBe(
      'stale',
    );
    expect(result.current.state.details[JOB_A]?.data?.extraction?.summary).toBe(
      'New extraction',
    );
    expect(result.current.state.externalInvalidation.graphGeneration).toBe(1);
    expect(evaluateSavedJob).not.toHaveBeenCalled();
  });

  it('blocks duplicate reextract while pending', async () => {
    const gate = deferred<ReextractJobResponse>();
    const reextractSavedJob = vi.fn().mockReturnValue(gate.promise);
    const {result} = renderHook(() =>
      useSavedJobsState({api: {reextractSavedJob}}),
    );

    let first!: Promise<'success' | 'duplicate' | 'error'>;
    let second!: Promise<'success' | 'duplicate' | 'error'>;
    act(() => {
      first = result.current.confirmReextract(JOB_A);
      second = result.current.confirmReextract(JOB_A);
    });
    expect(await second).toBe('duplicate');
    await act(async () => {
      gate.resolve(reextractResponse(JOB_A));
      await first;
    });
    expect(reextractSavedJob).toHaveBeenCalledTimes(1);
  });
});

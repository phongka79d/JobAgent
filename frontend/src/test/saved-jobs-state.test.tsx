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
  SavedJobDetail,
  SavedJobListItem,
  SavedJobListPage,
} from '../features/jobs/types';

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
    extraction: null,
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
});

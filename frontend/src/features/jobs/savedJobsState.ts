/**
 * Sidebar-local saved-JD request/cache/action state (Plan 10 / Master §15.6).
 * Independent list/detail/action loading; successful-page cache; request-order
 * guards; focused list/detail invalidation plus graph/chat generation bumps.
 * Does not own observability panels, chat SSE, or MatchResult formatting.
 */

import {useCallback, useReducer, useRef} from 'react';

import {ChatApiError} from '../../lib/api/chat';
import {useLatestRequest} from '../observability/useLatestRequest';
import {
  defaultSavedJobsApi,
  toSavedJobActionError,
  type SavedJobsApi,
} from './api';
import {
  selectSafeRemainingJobId,
  type EvaluateJobResponse,
  type SaveAndEvaluateResponse,
  type SavedJobDetail,
  type SavedJobListItem,
  type SavedJobListPage,
  type SavedJobsPageQuery,
  type SavedJobsSafeError,
} from './types';

export type {SavedJobsSafeError};
export {selectSafeRemainingJobId};

export type RequestPhase =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'error';

export type CachedResource<T> = {
  phase: RequestPhase;
  data: T | null;
  error: SavedJobsSafeError | null;
  /** True after at least one successful fetch for this cache key. */
  loaded: boolean;
};

/** Per-Job action kinds (at most one pending per job_id). */
export type SavedJobActionKind = 'evaluate' | 'delete';

export type SavedJobsActionSlice = {
  pendingByJob: Readonly<Record<string, SavedJobActionKind>>;
  errorsByJob: Readonly<Record<string, SavedJobsSafeError>>;
  /** source_message_id → save-and-evaluate in flight. */
  pendingSaveByMessage: Readonly<Record<string, true>>;
  saveErrorsByMessage: Readonly<Record<string, SavedJobsSafeError>>;
};

/**
 * Generations for projections owned outside this module.
 * UI/composition reloads graph / chat cards when these change.
 */
export type SavedJobsExternalInvalidation = {
  graphGeneration: number;
  chatCardGeneration: number;
};

export type SavedJobsState = {
  selectedJobId: string | null;
  list: CachedResource<SavedJobListPage>;
  /** Cache key: jobId */
  details: Record<string, CachedResource<SavedJobDetail>>;
  actions: SavedJobsActionSlice;
  externalInvalidation: SavedJobsExternalInvalidation;
};

const emptyResource = <T,>(): CachedResource<T> => ({
  phase: 'idle',
  data: null,
  error: null,
  loaded: false,
});

export const initialSavedJobsActionSlice: SavedJobsActionSlice = {
  pendingByJob: {},
  errorsByJob: {},
  pendingSaveByMessage: {},
  saveErrorsByMessage: {},
};

export const initialSavedJobsState: SavedJobsState = {
  selectedJobId: null,
  list: emptyResource(),
  details: {},
  actions: initialSavedJobsActionSlice,
  externalInvalidation: {
    graphGeneration: 0,
    chatCardGeneration: 0,
  },
};

export function isJobActionPending(
  slice: SavedJobsActionSlice,
  jobId: string,
): boolean {
  return slice.pendingByJob[jobId] !== undefined;
}

export function isJobActionKindPending(
  slice: SavedJobsActionSlice,
  jobId: string,
  kind: SavedJobActionKind,
): boolean {
  return slice.pendingByJob[jobId] === kind;
}

function dropPendingJob(
  pending: Readonly<Record<string, SavedJobActionKind>>,
  jobId: string,
): Record<string, SavedJobActionKind> {
  if (!(jobId in pending)) {
    return pending as Record<string, SavedJobActionKind>;
  }
  const next = {...pending};
  delete next[jobId];
  return next;
}

function dropJobError(
  errors: Readonly<Record<string, SavedJobsSafeError>>,
  jobId: string,
): Record<string, SavedJobsSafeError> {
  if (!(jobId in errors)) {
    return errors as Record<string, SavedJobsSafeError>;
  }
  const next = {...errors};
  delete next[jobId];
  return next;
}

function toSafeError(err: unknown): SavedJobsSafeError {
  if (err instanceof ChatApiError) {
    return {code: err.code, summary: err.summary};
  }
  if (err instanceof Error) {
    return {code: 'REQUEST_FAILED', summary: err.message};
  }
  return {code: 'REQUEST_FAILED', summary: 'Request failed'};
}

function phaseForPage(itemCount: number): RequestPhase {
  return itemCount === 0 ? 'empty' : 'ready';
}

function applySuccess<T>(data: T, itemCount: number): CachedResource<T> {
  return {
    phase: phaseForPage(itemCount),
    data,
    error: null,
    loaded: true,
  };
}

function applyError<T>(
  prev: CachedResource<T>,
  error: SavedJobsSafeError,
): CachedResource<T> {
  return {
    phase: 'error',
    data: prev.data,
    error,
    loaded: prev.loaded,
  };
}

function applyLoading<T>(prev: CachedResource<T>): CachedResource<T> {
  return {
    phase: 'loading',
    data: prev.data,
    error: null,
    loaded: prev.loaded,
  };
}

function bumpExternal(
  prev: SavedJobsExternalInvalidation,
): SavedJobsExternalInvalidation {
  return {
    graphGeneration: prev.graphGeneration + 1,
    chatCardGeneration: prev.chatCardGeneration + 1,
  };
}

function patchListItem(
  page: SavedJobListPage | null,
  job: SavedJobListItem,
): SavedJobListPage | null {
  if (page === null) {
    return null;
  }
  const index = page.items.findIndex((item) => item.id === job.id);
  if (index < 0) {
    return {
      items: [job, ...page.items],
      next_cursor: page.next_cursor,
    };
  }
  const items = page.items.slice();
  items[index] = job;
  return {items, next_cursor: page.next_cursor};
}

function patchDetailAfterEvaluate(
  prev: CachedResource<SavedJobDetail> | undefined,
  response: EvaluateJobResponse,
): CachedResource<SavedJobDetail> {
  const prior = prev?.data ?? null;
  const nextDetail: SavedJobDetail = {
    compact: response.job,
    extraction: prior?.extraction ?? null,
    raw_content: prior?.raw_content ?? null,
    latest_evaluation: response.evaluation,
  };
  return {
    phase: 'ready',
    data: nextDetail,
    error: null,
    loaded: true,
  };
}

type Action =
  | {type: 'select_job'; jobId: string | null}
  | {type: 'list_loading'}
  | {type: 'list_success'; data: SavedJobListPage}
  | {type: 'list_error'; error: SavedJobsSafeError}
  | {type: 'detail_loading'; jobId: string}
  | {type: 'detail_success'; jobId: string; data: SavedJobDetail}
  | {type: 'detail_error'; jobId: string; error: SavedJobsSafeError}
  | {
      type: 'action_begin';
      jobId: string;
      kind: SavedJobActionKind;
    }
  | {type: 'action_end'; jobId: string}
  | {
      type: 'action_error';
      jobId: string;
      error: SavedJobsSafeError;
    }
  | {type: 'clear_action_error'; jobId: string}
  | {
      type: 'evaluate_success';
      jobId: string;
      response: EvaluateJobResponse;
    }
  | {
      type: 'delete_success';
      jobId: string;
    }
  | {
      type: 'save_begin';
      sourceMessageId: string;
    }
  | {
      type: 'save_end';
      sourceMessageId: string;
    }
  | {
      type: 'save_error';
      sourceMessageId: string;
      error: SavedJobsSafeError;
    }
  | {
      type: 'save_success';
      sourceMessageId: string;
      response: SaveAndEvaluateResponse;
    };

export function savedJobsReducer(
  state: SavedJobsState,
  action: Action,
): SavedJobsState {
  switch (action.type) {
    case 'select_job':
      return {...state, selectedJobId: action.jobId};
    case 'list_loading':
      return {...state, list: applyLoading(state.list)};
    case 'list_success':
      return {
        ...state,
        list: applySuccess(action.data, action.data.items.length),
      };
    case 'list_error':
      return {...state, list: applyError(state.list, action.error)};
    case 'detail_loading': {
      const prev =
        state.details[action.jobId] ?? emptyResource<SavedJobDetail>();
      return {
        ...state,
        details: {
          ...state.details,
          [action.jobId]: applyLoading(prev),
        },
      };
    }
    case 'detail_success':
      return {
        ...state,
        details: {
          ...state.details,
          [action.jobId]: {
            phase: 'ready',
            data: action.data,
            error: null,
            loaded: true,
          },
        },
      };
    case 'detail_error': {
      const prev =
        state.details[action.jobId] ?? emptyResource<SavedJobDetail>();
      return {
        ...state,
        details: {
          ...state.details,
          [action.jobId]: applyError(prev, action.error),
        },
      };
    }
    case 'action_begin': {
      if (isJobActionPending(state.actions, action.jobId)) {
        return state;
      }
      return {
        ...state,
        actions: {
          ...state.actions,
          pendingByJob: {
            ...state.actions.pendingByJob,
            [action.jobId]: action.kind,
          },
          errorsByJob: dropJobError(state.actions.errorsByJob, action.jobId),
        },
      };
    }
    case 'action_end':
      return {
        ...state,
        actions: {
          ...state.actions,
          pendingByJob: dropPendingJob(
            state.actions.pendingByJob,
            action.jobId,
          ),
        },
      };
    case 'action_error':
      return {
        ...state,
        actions: {
          ...state.actions,
          pendingByJob: dropPendingJob(
            state.actions.pendingByJob,
            action.jobId,
          ),
          errorsByJob: {
            ...state.actions.errorsByJob,
            [action.jobId]: action.error,
          },
        },
      };
    case 'clear_action_error':
      return {
        ...state,
        actions: {
          ...state.actions,
          errorsByJob: dropJobError(state.actions.errorsByJob, action.jobId),
        },
      };
    case 'evaluate_success': {
      const listData = patchListItem(state.list.data, action.response.job);
      const nextDetails = {
        ...state.details,
        [action.jobId]: patchDetailAfterEvaluate(
          state.details[action.jobId],
          action.response,
        ),
      };
      return {
        ...state,
        list: listData
          ? {
              phase: phaseForPage(listData.items.length),
              data: listData,
              error: null,
              loaded: state.list.loaded || true,
            }
          : state.list,
        details: nextDetails,
        actions: {
          ...state.actions,
          pendingByJob: dropPendingJob(
            state.actions.pendingByJob,
            action.jobId,
          ),
          errorsByJob: dropJobError(state.actions.errorsByJob, action.jobId),
        },
        externalInvalidation: bumpExternal(state.externalInvalidation),
      };
    }
    case 'delete_success': {
      const priorItems = state.list.data?.items ?? [];
      const remainingItems = priorItems.filter(
        (item) => item.id !== action.jobId,
      );
      const nextSelection = selectSafeRemainingJobId(
        priorItems,
        action.jobId,
        state.selectedJobId,
      );
      const nextDetails = {...state.details};
      delete nextDetails[action.jobId];
      const page: SavedJobListPage = {
        items: remainingItems,
        next_cursor: state.list.data?.next_cursor ?? null,
      };
      return {
        ...state,
        selectedJobId: nextSelection,
        list: {
          phase: remainingItems.length === 0 ? 'empty' : 'ready',
          data: page,
          error: null,
          loaded: true,
        },
        details: nextDetails,
        actions: {
          ...state.actions,
          pendingByJob: dropPendingJob(
            state.actions.pendingByJob,
            action.jobId,
          ),
          errorsByJob: dropJobError(state.actions.errorsByJob, action.jobId),
        },
        externalInvalidation: bumpExternal(state.externalInvalidation),
      };
    }
    case 'save_begin': {
      if (state.actions.pendingSaveByMessage[action.sourceMessageId]) {
        return state;
      }
      const nextErrors = {...state.actions.saveErrorsByMessage};
      delete nextErrors[action.sourceMessageId];
      return {
        ...state,
        actions: {
          ...state.actions,
          pendingSaveByMessage: {
            ...state.actions.pendingSaveByMessage,
            [action.sourceMessageId]: true,
          },
          saveErrorsByMessage: nextErrors,
        },
      };
    }
    case 'save_end': {
      const nextPending = {...state.actions.pendingSaveByMessage};
      delete nextPending[action.sourceMessageId];
      return {
        ...state,
        actions: {
          ...state.actions,
          pendingSaveByMessage: nextPending,
        },
      };
    }
    case 'save_error': {
      const nextPending = {...state.actions.pendingSaveByMessage};
      delete nextPending[action.sourceMessageId];
      return {
        ...state,
        actions: {
          ...state.actions,
          pendingSaveByMessage: nextPending,
          saveErrorsByMessage: {
            ...state.actions.saveErrorsByMessage,
            [action.sourceMessageId]: action.error,
          },
        },
      };
    }
    case 'save_success': {
      const nextPending = {...state.actions.pendingSaveByMessage};
      delete nextPending[action.sourceMessageId];
      const nextErrors = {...state.actions.saveErrorsByMessage};
      delete nextErrors[action.sourceMessageId];
      const listData = patchListItem(state.list.data, action.response.job);
      const jobId = action.response.job.id;
      const nextDetails = {...state.details};
      if (action.response.evaluation) {
        const prior = nextDetails[jobId];
        nextDetails[jobId] = {
          phase: 'ready',
          data: {
            compact: action.response.job,
            extraction: prior?.data?.extraction ?? null,
            raw_content: prior?.data?.raw_content ?? null,
            latest_evaluation: action.response.evaluation,
          },
          error: null,
          loaded: true,
        };
      } else if (listData) {
        // Unavailable: keep prior detail extraction if any; patch compact only.
        const prior = nextDetails[jobId];
        if (prior?.data) {
          nextDetails[jobId] = {
            ...prior,
            data: {
              ...prior.data,
              compact: action.response.job,
            },
            error: null,
          };
        }
      }
      return {
        ...state,
        list: listData
          ? {
              phase: phaseForPage(listData.items.length),
              data: listData,
              error: null,
              loaded: true,
            }
          : {
              // First list load not yet done — force reload via unloaded list.
              ...state.list,
              loaded: false,
            },
        details: nextDetails,
        actions: {
          ...state.actions,
          pendingSaveByMessage: nextPending,
          saveErrorsByMessage: nextErrors,
        },
        externalInvalidation: bumpExternal(state.externalInvalidation),
      };
    }
    default:
      return state;
  }
}

export type UseSavedJobsOptions = {
  api?: Partial<SavedJobsApi>;
};

export function useSavedJobsState(options: UseSavedJobsOptions = {}) {
  const api: SavedJobsApi = {
    ...defaultSavedJobsApi,
    ...options.api,
  };
  const [state, dispatch] = useReducer(
    savedJobsReducer,
    initialSavedJobsState,
  );
  const beginLatestRequest = useLatestRequest();
  /** Synchronous pending guard so rapid double-clicks cannot race re-render. */
  const actionInFlightRef = useRef<Set<string>>(new Set());
  const saveInFlightRef = useRef<Set<string>>(new Set());

  const selectJob = useCallback((jobId: string | null) => {
    dispatch({type: 'select_job', jobId});
  }, []);

  const clearActionError = useCallback((jobId: string) => {
    dispatch({type: 'clear_action_error', jobId});
  }, []);

  const loadList = useCallback(
    async (
      query: SavedJobsPageQuery = {},
      opts?: {force?: boolean; signal?: AbortSignal},
    ) => {
      if (state.list.loaded && !opts?.force) {
        return;
      }
      const isLatest = beginLatestRequest('saved-jobs-list');
      dispatch({type: 'list_loading'});
      try {
        const data = await api.fetchSavedJobs(query, opts?.signal);
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'list_success', data});
      } catch (err) {
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'list_error', error: toSafeError(err)});
      }
    },
    [api, beginLatestRequest, state.list.loaded],
  );

  const loadDetail = useCallback(
    async (
      jobId: string,
      opts?: {force?: boolean; signal?: AbortSignal},
    ) => {
      const cached = state.details[jobId];
      if (cached?.loaded && !opts?.force) {
        return;
      }
      const isLatest = beginLatestRequest(`saved-job-detail:${jobId}`);
      dispatch({type: 'detail_loading', jobId});
      try {
        const data = await api.fetchSavedJobDetail(jobId, opts?.signal);
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'detail_success', jobId, data});
      } catch (err) {
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({
          type: 'detail_error',
          jobId,
          error: toSafeError(err),
        });
      }
    },
    [api, beginLatestRequest, state.details],
  );

  const evaluateJob = useCallback(
    async (
      jobId: string,
      opts?: {signal?: AbortSignal},
    ): Promise<'success' | 'duplicate' | 'error'> => {
      if (actionInFlightRef.current.has(jobId)) {
        return 'duplicate';
      }
      actionInFlightRef.current.add(jobId);
      dispatch({type: 'action_begin', jobId, kind: 'evaluate'});
      try {
        const response = await api.evaluateSavedJob(jobId, opts?.signal);
        if (opts?.signal?.aborted) {
          actionInFlightRef.current.delete(jobId);
          dispatch({type: 'action_end', jobId});
          return 'error';
        }
        actionInFlightRef.current.delete(jobId);
        dispatch({type: 'evaluate_success', jobId, response});
        return 'success';
      } catch (err) {
        actionInFlightRef.current.delete(jobId);
        if (opts?.signal?.aborted) {
          dispatch({type: 'action_end', jobId});
          return 'error';
        }
        const safe = toSavedJobActionError(err);
        dispatch({
          type: 'action_error',
          jobId,
          error: {code: safe.code, summary: safe.summary},
        });
        return 'error';
      }
    },
    [api],
  );

  const confirmDelete = useCallback(
    async (
      jobId: string,
      opts?: {signal?: AbortSignal},
    ): Promise<'success' | 'duplicate' | 'error'> => {
      if (actionInFlightRef.current.has(jobId)) {
        return 'duplicate';
      }
      actionInFlightRef.current.add(jobId);
      dispatch({type: 'action_begin', jobId, kind: 'delete'});
      try {
        await api.deleteSavedJob(jobId, opts?.signal);
        if (opts?.signal?.aborted) {
          actionInFlightRef.current.delete(jobId);
          dispatch({type: 'action_end', jobId});
          return 'error';
        }
        actionInFlightRef.current.delete(jobId);
        dispatch({type: 'delete_success', jobId});
        return 'success';
      } catch (err) {
        actionInFlightRef.current.delete(jobId);
        if (opts?.signal?.aborted) {
          dispatch({type: 'action_end', jobId});
          return 'error';
        }
        const safe = toSavedJobActionError(err);
        dispatch({
          type: 'action_error',
          jobId,
          error: {code: safe.code, summary: safe.summary},
        });
        return 'error';
      }
    },
    [api],
  );

  const saveAndEvaluate = useCallback(
    async (
      sourceMessageId: string,
      opts?: {signal?: AbortSignal},
    ): Promise<'success' | 'duplicate' | 'error'> => {
      if (saveInFlightRef.current.has(sourceMessageId)) {
        return 'duplicate';
      }
      saveInFlightRef.current.add(sourceMessageId);
      dispatch({type: 'save_begin', sourceMessageId});
      try {
        const response = await api.saveAndEvaluateJob(
          sourceMessageId,
          opts?.signal,
        );
        if (opts?.signal?.aborted) {
          saveInFlightRef.current.delete(sourceMessageId);
          dispatch({type: 'save_end', sourceMessageId});
          return 'error';
        }
        saveInFlightRef.current.delete(sourceMessageId);
        dispatch({type: 'save_success', sourceMessageId, response});
        return 'success';
      } catch (err) {
        saveInFlightRef.current.delete(sourceMessageId);
        if (opts?.signal?.aborted) {
          dispatch({type: 'save_end', sourceMessageId});
          return 'error';
        }
        const safe = toSavedJobActionError(err);
        dispatch({
          type: 'save_error',
          sourceMessageId,
          error: {code: safe.code, summary: safe.summary},
        });
        return 'error';
      }
    },
    [api],
  );

  return {
    state,
    selectJob,
    clearActionError,
    loadList,
    loadDetail,
    evaluateJob,
    confirmDelete,
    saveAndEvaluate,
    isJobActionPending: (jobId: string) =>
      isJobActionPending(state.actions, jobId),
    isJobActionKindPending: (jobId: string, kind: SavedJobActionKind) =>
      isJobActionKindPending(state.actions, jobId, kind),
  };
}

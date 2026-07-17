/**
 * Sidebar-local observability state: tabs, selection, query cache, request status.
 * CV Manager pending actions + focused invalidation (Plan 9).
 * Does not own profile/upload or chat/SSE state (reprocess streams via ChatPage).
 */

import {useCallback, useReducer, useRef} from 'react';

import {ChatApiError} from '../../lib/api/chat';
import type {ObservabilityApi} from './api';
import {defaultObservabilityApi} from './api';
import {
  dropActionError,
  dropPendingAttachment,
  initialCvManagerActionSlice,
  isCvActionPending,
  selectSafeRemainingAttachmentId,
  type CvManagerActionSlice,
  type CvManagerDispatchAction,
} from './cvManagerState';
import {toCvManagerActionError} from './cvManagerTypes';
import type {
  ChunkDetail,
  ChunkListPage,
  CvHistoryItem,
  CvHistoryPage,
  GraphSnapshot,
  ObservabilitySafeError,
  ObservabilityTabId,
  RunHistoryPage,
} from './types';
import {useLatestRequest} from './useLatestRequest';

export type {
  CvManagerActionKind,
  CvManagerActionSlice,
} from './cvManagerState';
export {isCvActionPending, selectSafeRemainingAttachmentId};

export type RequestPhase =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'error';

export type CachedResource<T> = {
  phase: RequestPhase;
  data: T | null;
  error: ObservabilitySafeError | null;
  /** True after at least one successful fetch for this cache key. */
  loaded: boolean;
};

export type ObservabilityState = {
  selectedTab: ObservabilityTabId;
  selectedAttachmentId: string | null;
  expandedChunkOrdinal: number | null;
  expandedRunId: string | null;
  cvHistory: CachedResource<CvHistoryPage>;
  /** Cache key: attachmentId */
  chunkLists: Record<string, CachedResource<ChunkListPage>>;
  /** Cache key: `${attachmentId}:${ordinal}` */
  chunkDetails: Record<string, CachedResource<ChunkDetail>>;
  runs: CachedResource<RunHistoryPage>;
  graph: CachedResource<GraphSnapshot>;
  /** Sidebar-local CV Manager pending/error maps (Master §15.6). */
  cvManager: CvManagerActionSlice;
};

const emptyResource = <T,>(): CachedResource<T> => ({
  phase: 'idle',
  data: null,
  error: null,
  loaded: false,
});

export const initialObservabilityState: ObservabilityState = {
  selectedTab: 'overview',
  selectedAttachmentId: null,
  expandedChunkOrdinal: null,
  expandedRunId: null,
  cvHistory: emptyResource(),
  chunkLists: {},
  chunkDetails: {},
  runs: emptyResource(),
  graph: emptyResource(),
  cvManager: initialCvManagerActionSlice,
};

export function chunkDetailKey(attachmentId: string, ordinal: number): string {
  return `${attachmentId}:${ordinal}`;
}

function toSafeError(err: unknown): ObservabilitySafeError {
  if (err instanceof ChatApiError) {
    return {code: err.code, summary: err.summary};
  }
  if (err instanceof Error) {
    return {code: 'REQUEST_FAILED', summary: err.message};
  }
  return {code: 'REQUEST_FAILED', summary: 'Request failed'};
}

type Action =
  | {type: 'select_tab'; tab: ObservabilityTabId}
  | {type: 'select_attachment'; attachmentId: string | null}
  | {type: 'set_expanded_chunk'; ordinal: number | null}
  | {type: 'set_expanded_run'; runId: string | null}
  | {
      type: 'resource_loading';
      resource: 'cvHistory' | 'runs' | 'graph';
    }
  | {
      type: 'resource_success';
      resource: 'cvHistory';
      data: CvHistoryPage;
    }
  | {
      type: 'resource_success';
      resource: 'runs';
      data: RunHistoryPage;
    }
  | {
      type: 'resource_success';
      resource: 'graph';
      data: GraphSnapshot;
    }
  | {
      type: 'resource_error';
      resource: 'cvHistory' | 'runs' | 'graph';
      error: ObservabilitySafeError;
    }
  | {
      type: 'chunk_list_loading';
      attachmentId: string;
    }
  | {
      type: 'chunk_list_success';
      attachmentId: string;
      data: ChunkListPage;
    }
  | {
      type: 'chunk_list_error';
      attachmentId: string;
      error: ObservabilitySafeError;
    }
  | {
      type: 'chunk_detail_loading';
      attachmentId: string;
      ordinal: number;
    }
  | {
      type: 'chunk_detail_success';
      attachmentId: string;
      ordinal: number;
      data: ChunkDetail;
    }
  | {
      type: 'chunk_detail_error';
      attachmentId: string;
      ordinal: number;
      error: ObservabilitySafeError;
    }
  | CvManagerDispatchAction;

function phaseForPage(itemCount: number): RequestPhase {
  return itemCount === 0 ? 'empty' : 'ready';
}

function applySuccess<T>(
  data: T,
  itemCount: number,
): CachedResource<T> {
  return {
    phase: phaseForPage(itemCount),
    data,
    error: null,
    loaded: true,
  };
}

function applyError<T>(
  prev: CachedResource<T>,
  error: ObservabilitySafeError,
): CachedResource<T> {
  return {
    // Keep prior safe data after failure (stale-on-error).
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

export function observabilityReducer(
  state: ObservabilityState,
  action: Action,
): ObservabilityState {
  switch (action.type) {
    case 'select_tab':
      return {...state, selectedTab: action.tab};
    case 'select_attachment':
      return {
        ...state,
        selectedAttachmentId: action.attachmentId,
        expandedChunkOrdinal: null,
      };
    case 'set_expanded_chunk':
      return {...state, expandedChunkOrdinal: action.ordinal};
    case 'set_expanded_run':
      return {...state, expandedRunId: action.runId};
    case 'resource_loading':
      if (action.resource === 'cvHistory') {
        return {...state, cvHistory: applyLoading(state.cvHistory)};
      }
      if (action.resource === 'runs') {
        return {...state, runs: applyLoading(state.runs)};
      }
      return {...state, graph: applyLoading(state.graph)};
    case 'resource_success':
      if (action.resource === 'cvHistory') {
        return {
          ...state,
          cvHistory: applySuccess(action.data, action.data.items.length),
        };
      }
      if (action.resource === 'runs') {
        return {
          ...state,
          runs: applySuccess(action.data, action.data.items.length),
        };
      }
      return {
        ...state,
        graph: {
          phase: 'ready',
          data: action.data,
          error: null,
          loaded: true,
        },
      };
    case 'resource_error':
      if (action.resource === 'cvHistory') {
        return {
          ...state,
          cvHistory: applyError(state.cvHistory, action.error),
        };
      }
      if (action.resource === 'runs') {
        return {...state, runs: applyError(state.runs, action.error)};
      }
      return {...state, graph: applyError(state.graph, action.error)};
    case 'chunk_list_loading': {
      const prev = state.chunkLists[action.attachmentId] ?? emptyResource<ChunkListPage>();
      return {
        ...state,
        chunkLists: {
          ...state.chunkLists,
          [action.attachmentId]: applyLoading(prev),
        },
      };
    }
    case 'chunk_list_success': {
      return {
        ...state,
        chunkLists: {
          ...state.chunkLists,
          [action.attachmentId]: applySuccess(
            action.data,
            action.data.items.length,
          ),
        },
      };
    }
    case 'chunk_list_error': {
      const prev = state.chunkLists[action.attachmentId] ?? emptyResource<ChunkListPage>();
      return {
        ...state,
        chunkLists: {
          ...state.chunkLists,
          [action.attachmentId]: applyError(prev, action.error),
        },
      };
    }
    case 'chunk_detail_loading': {
      const key = chunkDetailKey(action.attachmentId, action.ordinal);
      const prev = state.chunkDetails[key] ?? emptyResource<ChunkDetail>();
      return {
        ...state,
        expandedChunkOrdinal: action.ordinal,
        chunkDetails: {
          ...state.chunkDetails,
          [key]: applyLoading(prev),
        },
      };
    }
    case 'chunk_detail_success': {
      const key = chunkDetailKey(action.attachmentId, action.ordinal);
      return {
        ...state,
        chunkDetails: {
          ...state.chunkDetails,
          [key]: {
            phase: 'ready',
            data: action.data,
            error: null,
            loaded: true,
          },
        },
      };
    }
    case 'chunk_detail_error': {
      const key = chunkDetailKey(action.attachmentId, action.ordinal);
      const prev = state.chunkDetails[key] ?? emptyResource<ChunkDetail>();
      return {
        ...state,
        chunkDetails: {
          ...state.chunkDetails,
          [key]: applyError(prev, action.error),
        },
      };
    }
    case 'cv_action_begin': {
      if (isCvActionPending(state.cvManager, action.attachmentId)) {
        return state;
      }
      return {
        ...state,
        cvManager: {
          pendingByAttachment: {
            ...state.cvManager.pendingByAttachment,
            [action.attachmentId]: action.kind,
          },
          errorsByAttachment: dropActionError(
            state.cvManager.errorsByAttachment,
            action.attachmentId,
          ),
        },
      };
    }
    case 'cv_action_end': {
      return {
        ...state,
        cvManager: {
          ...state.cvManager,
          pendingByAttachment: dropPendingAttachment(
            state.cvManager.pendingByAttachment,
            action.attachmentId,
          ),
        },
      };
    }
    case 'cv_action_error': {
      return {
        ...state,
        cvManager: {
          pendingByAttachment: dropPendingAttachment(
            state.cvManager.pendingByAttachment,
            action.attachmentId,
          ),
          errorsByAttachment: {
            ...state.cvManager.errorsByAttachment,
            [action.attachmentId]: action.error,
          },
        },
      };
    }
    case 'cv_clear_action_error': {
      return {
        ...state,
        cvManager: {
          ...state.cvManager,
          errorsByAttachment: dropActionError(
            state.cvManager.errorsByAttachment,
            action.attachmentId,
          ),
        },
      };
    }
    case 'cv_delete_success': {
      // Invalidate only CV list, chunks for deleted id, runs, and graph.
      const remainingItems = action.remainingItems as CvHistoryItem[];
      const nextSelection = selectSafeRemainingAttachmentId(
        remainingItems,
        action.attachmentId,
        state.selectedAttachmentId,
      );
      const nextChunkLists: Record<string, CachedResource<ChunkListPage>> = {
        ...state.chunkLists,
      };
      delete nextChunkLists[action.attachmentId];
      const nextChunkDetails: Record<string, CachedResource<ChunkDetail>> = {};
      const prefix = `${action.attachmentId}:`;
      for (const [key, value] of Object.entries(state.chunkDetails)) {
        if (!key.startsWith(prefix)) {
          nextChunkDetails[key] = value;
        }
      }
      const page: CvHistoryPage = {
        items: remainingItems,
        next_cursor: state.cvHistory.data?.next_cursor ?? null,
      };
      return {
        ...state,
        selectedAttachmentId: nextSelection,
        expandedChunkOrdinal:
          state.selectedAttachmentId === action.attachmentId
            ? null
            : state.expandedChunkOrdinal,
        cvHistory: {
          phase: remainingItems.length === 0 ? 'empty' : 'ready',
          data: page,
          error: null,
          loaded: true,
        },
        chunkLists: nextChunkLists,
        chunkDetails: nextChunkDetails,
        runs: emptyResource<RunHistoryPage>(),
        graph: emptyResource<GraphSnapshot>(),
        cvManager: {
          pendingByAttachment: dropPendingAttachment(
            state.cvManager.pendingByAttachment,
            action.attachmentId,
          ),
          errorsByAttachment: dropActionError(
            state.cvManager.errorsByAttachment,
            action.attachmentId,
          ),
        },
      };
    }
    case 'cv_invalidate_activation': {
      // After approval activates a reprocessed CV — force list/chunks/runs/graph reload.
      // Active selection stays until list refresh; profile summary is composition-owned.
      return {
        ...state,
        cvHistory: emptyResource<CvHistoryPage>(),
        chunkLists: {},
        chunkDetails: {},
        runs: emptyResource<RunHistoryPage>(),
        graph: emptyResource<GraphSnapshot>(),
      };
    }
    default:
      return state;
  }
}

export type UseObservabilityOptions = {
  api?: Partial<ObservabilityApi>;
};

export function useObservabilityState(options: UseObservabilityOptions = {}) {
  const api: ObservabilityApi = {
    ...defaultObservabilityApi,
    ...options.api,
  };
  const [state, dispatch] = useReducer(
    observabilityReducer,
    initialObservabilityState,
  );
  const beginLatestRequest = useLatestRequest();
  /** Synchronous pending guard so rapid double-clicks cannot race re-render. */
  const actionInFlightRef = useRef<Set<string>>(new Set());

  const selectTab = useCallback((tab: ObservabilityTabId) => {
    dispatch({type: 'select_tab', tab});
  }, []);

  const selectAttachment = useCallback((attachmentId: string | null) => {
    dispatch({type: 'select_attachment', attachmentId});
  }, []);

  const setExpandedRun = useCallback((runId: string | null) => {
    dispatch({type: 'set_expanded_run', runId});
  }, []);

  const collapseChunk = useCallback(() => {
    dispatch({type: 'set_expanded_chunk', ordinal: null});
  }, []);

  const loadCvHistory = useCallback(
    async (opts?: {force?: boolean; signal?: AbortSignal}) => {
      if (state.cvHistory.loaded && !opts?.force) {
        return;
      }
      const isLatest = beginLatestRequest('cv-history');
      dispatch({type: 'resource_loading', resource: 'cvHistory'});
      try {
        const data = await api.fetchCvHistory({}, opts?.signal);
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'resource_success', resource: 'cvHistory', data});
      } catch (err) {
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({
          type: 'resource_error',
          resource: 'cvHistory',
          error: toSafeError(err),
        });
      }
    },
    [api, beginLatestRequest, state.cvHistory.loaded],
  );

  const loadRuns = useCallback(
    async (opts?: {force?: boolean; signal?: AbortSignal}) => {
      if (state.runs.loaded && !opts?.force) {
        return;
      }
      const isLatest = beginLatestRequest('runs');
      dispatch({type: 'resource_loading', resource: 'runs'});
      try {
        const data = await api.fetchRunHistory({}, opts?.signal);
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'resource_success', resource: 'runs', data});
      } catch (err) {
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({
          type: 'resource_error',
          resource: 'runs',
          error: toSafeError(err),
        });
      }
    },
    [api, beginLatestRequest, state.runs.loaded],
  );

  const loadGraph = useCallback(
    async (opts?: {force?: boolean; signal?: AbortSignal}) => {
      if (state.graph.loaded && !opts?.force) {
        return;
      }
      const isLatest = beginLatestRequest('graph');
      dispatch({type: 'resource_loading', resource: 'graph'});
      try {
        const data = await api.fetchGraphSnapshot(opts?.signal);
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'resource_success', resource: 'graph', data});
      } catch (err) {
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({
          type: 'resource_error',
          resource: 'graph',
          error: toSafeError(err),
        });
      }
    },
    [api, beginLatestRequest, state.graph.loaded],
  );

  const loadChunkList = useCallback(
    async (
      attachmentId: string,
      opts?: {force?: boolean; signal?: AbortSignal},
    ) => {
      const cached = state.chunkLists[attachmentId];
      if (cached?.loaded && !opts?.force) {
        return;
      }
      const isLatest = beginLatestRequest(`chunk-list:${attachmentId}`);
      dispatch({type: 'chunk_list_loading', attachmentId});
      try {
        const data = await api.fetchChunkList(attachmentId, {}, opts?.signal);
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({type: 'chunk_list_success', attachmentId, data});
      } catch (err) {
        if (opts?.signal?.aborted || !isLatest()) {
          return;
        }
        dispatch({
          type: 'chunk_list_error',
          attachmentId,
          error: toSafeError(err),
        });
      }
    },
    [api, beginLatestRequest, state.chunkLists],
  );

  const expandChunk = useCallback(
    async (
      attachmentId: string,
      ordinal: number,
      opts?: {signal?: AbortSignal},
    ) => {
      const key = chunkDetailKey(attachmentId, ordinal);
      const cached = state.chunkDetails[key];
      if (
        cached?.phase === 'loading' ||
        (cached?.loaded && cached.data)
      ) {
        dispatch({type: 'set_expanded_chunk', ordinal});
        return;
      }
      dispatch({type: 'chunk_detail_loading', attachmentId, ordinal});
      try {
        const data = await api.fetchChunkDetail(
          attachmentId,
          ordinal,
          opts?.signal,
        );
        if (opts?.signal?.aborted) {
          return;
        }
        dispatch({
          type: 'chunk_detail_success',
          attachmentId,
          ordinal,
          data,
        });
      } catch (err) {
        if (opts?.signal?.aborted) {
          return;
        }
        dispatch({
          type: 'chunk_detail_error',
          attachmentId,
          ordinal,
          error: toSafeError(err),
        });
      }
    },
    [api, state.chunkDetails],
  );

  const openRetainedFile = useCallback(
    (attachmentId: string, fileAvailable: boolean) => {
      if (!fileAvailable) {
        return;
      }
      const url = api.getRetainedCvUrl(attachmentId);
      window.open(url, '_blank', 'noopener,noreferrer');
    },
    [api],
  );

  /**
   * Mark reprocess pending for one attachment. Returns false when duplicate.
   * Actual SSE stream is owned by ChatPage via streamCvReprocess.
   */
  const beginReprocess = useCallback((attachmentId: string): boolean => {
    if (actionInFlightRef.current.has(attachmentId)) {
      return false;
    }
    actionInFlightRef.current.add(attachmentId);
    dispatch({
      type: 'cv_action_begin',
      attachmentId,
      kind: 'reprocess',
    });
    return true;
  }, []);

  /** Clear reprocess pending after stream terminal / HTTP error (composition). */
  const endReprocess = useCallback((attachmentId: string) => {
    actionInFlightRef.current.delete(attachmentId);
    dispatch({type: 'cv_action_end', attachmentId});
  }, []);

  /** Record reprocess transport failure; retain list cache/selection. */
  const failReprocess = useCallback((attachmentId: string, err: unknown) => {
    actionInFlightRef.current.delete(attachmentId);
    const safe = toCvManagerActionError(err);
    dispatch({
      type: 'cv_action_error',
      attachmentId,
      error: {code: safe.code, summary: safe.summary},
    });
  }, []);

  /**
   * Confirmed delete: call DELETE, then invalidate only documented caches and
   * select a safe remaining row. Partial failure retains row/cache + retry text.
   */
  const confirmDelete = useCallback(
    async (
      attachmentId: string,
      opts?: {signal?: AbortSignal},
    ): Promise<'success' | 'duplicate' | 'error'> => {
      if (actionInFlightRef.current.has(attachmentId)) {
        return 'duplicate';
      }
      actionInFlightRef.current.add(attachmentId);
      dispatch({type: 'cv_action_begin', attachmentId, kind: 'delete'});
      try {
        await api.deleteCv(attachmentId, opts?.signal);
        if (opts?.signal?.aborted) {
          actionInFlightRef.current.delete(attachmentId);
          dispatch({type: 'cv_action_end', attachmentId});
          return 'error';
        }
        const priorItems = state.cvHistory.data?.items ?? [];
        const remainingItems = priorItems.filter(
          (item) => item.id !== attachmentId,
        );
        actionInFlightRef.current.delete(attachmentId);
        dispatch({
          type: 'cv_delete_success',
          attachmentId,
          remainingItems,
        });
        return 'success';
      } catch (err) {
        actionInFlightRef.current.delete(attachmentId);
        if (opts?.signal?.aborted) {
          dispatch({type: 'cv_action_end', attachmentId});
          return 'error';
        }
        const safe = toCvManagerActionError(err);
        dispatch({
          type: 'cv_action_error',
          attachmentId,
          error: {code: safe.code, summary: safe.summary},
        });
        return 'error';
      }
    },
    [api, state.cvHistory.data?.items],
  );

  /** Invalidate CV/chunk/run/graph caches after Save Profile activation. */
  const invalidateAfterActivation = useCallback(() => {
    dispatch({type: 'cv_invalidate_activation'});
  }, []);

  const clearActionError = useCallback((attachmentId: string) => {
    dispatch({type: 'cv_clear_action_error', attachmentId});
  }, []);

  return {
    state,
    api,
    selectTab,
    selectAttachment,
    setExpandedRun,
    collapseChunk,
    loadCvHistory,
    loadRuns,
    loadGraph,
    loadChunkList,
    expandChunk,
    openRetainedFile,
    beginReprocess,
    endReprocess,
    failReprocess,
    confirmDelete,
    invalidateAfterActivation,
    clearActionError,
  };
}

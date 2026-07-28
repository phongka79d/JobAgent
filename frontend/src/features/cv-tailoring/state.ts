import {useCallback, useEffect, useMemo, useRef, useState} from 'react';

import {ChatApiError} from '../../lib/api/chat';
import {
  defaultCvTailoringApi,
  type CvTailoringApi,
} from './api';
import {asTailoringErrorCode} from './types';
import type {
  CreateTailoringAiVersionRequest,
  CreateTailoringSessionRequest,
  TailoredCVContent,
  TailoringErrorCode,
  TailoringSessionDetailResponse,
  TailoringSessionListResponse,
  TailoringMutationOutcome,
  TailoringSseEvent,
} from './types';

export type TailoringRequestPhase =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'error'
  | 'disconnected';

export type TailoringSafeError = {
  readonly code: TailoringErrorCode | 'REQUEST_FAILED' | 'STREAM_DISCONNECTED';
  readonly summary: string;
};

export type TailoringResource<T> = {
  readonly phase: TailoringRequestPhase;
  readonly data: T | null;
  readonly error: TailoringSafeError | null;
};

export type CvTailoringState = {
  readonly profileScopeKey: string;
  readonly sessions: TailoringResource<TailoringSessionListResponse>;
  readonly selectedSessionId: string | null;
  readonly selectedVersionId: string | null;
  readonly detail: TailoringResource<TailoringSessionDetailResponse>;
  readonly draft: TailoredCVContent | null;
  readonly draftDirty: boolean;
  readonly conflict: boolean;
  readonly stream: TailoringResource<null>;
  readonly lastOutcome: TailoringMutationOutcome | null;
  readonly lastOutcomeSource: 'ai' | 'manual' | null;
};

export type UseCvTailoringOptions = {
  readonly profileId: string | null;
  readonly profileReady: boolean;
  readonly api?: Partial<CvTailoringApi>;
};

type MutationOperation = {
  readonly scope: string;
  readonly controller: AbortController;
};

type StreamRecovery =
  | {readonly kind: 'completed'; readonly detail: TailoringSessionDetailResponse}
  | {readonly kind: 'failed'; readonly error: TailoringSafeError}
  | {readonly kind: 'pending'}
  | {readonly kind: 'stale'};

const empty = <T,>(): TailoringResource<T> => ({
  phase: 'idle',
  data: null,
  error: null,
});

function scopeKey(profileId: string | null, ready: boolean): string {
  return `${profileId ?? 'none'}:${ready ? 'ready' : 'blocked'}`;
}

function initialState(key: string): CvTailoringState {
  return {
    profileScopeKey: key,
    sessions: empty(),
    selectedSessionId: null,
    selectedVersionId: null,
    detail: empty(),
    draft: null,
    draftDirty: false,
    conflict: false,
    stream: empty(),
    lastOutcome: null,
    lastOutcomeSource: null,
  };
}

function safeError(error: unknown): TailoringSafeError {
  if (error instanceof ChatApiError) {
    const code =
      error.code === 'REQUEST_FAILED'
        ? 'REQUEST_FAILED'
        : asTailoringErrorCode(error.code);
    if (code === null) {
      return {code: 'REQUEST_FAILED', summary: 'CV tailoring request failed'};
    }
    return {
      code,
      summary: error.summary,
    };
  }
  return {code: 'REQUEST_FAILED', summary: 'CV tailoring request failed'};
}

function streamError(event: TailoringSseEvent): TailoringSafeError | null {
  if (event.event !== 'run_failed') return null;
  const code = asTailoringErrorCode(event.payload.error_code);
  if (code === null) {
    return {code: 'REQUEST_FAILED', summary: 'CV tailoring request failed'};
  }
  return {
    code,
    summary: event.payload.summary,
  };
}

function isDurableCompletedDetail(
  detail: TailoringSessionDetailResponse,
): boolean {
  return (
    detail.session.state === 'ready' &&
    detail.session.currentness === 'current' &&
    detail.latest_run?.state === 'completed' &&
    detail.selected_version !== null &&
    detail.content !== null
  );
}

export function useCvTailoringState(options: UseCvTailoringOptions) {
  const key = scopeKey(options.profileId, options.profileReady);
  const api = useMemo<CvTailoringApi>(
    () => ({...defaultCvTailoringApi, ...options.api}),
    [options.api],
  );
  const [state, setState] = useState<CvTailoringState>(() => initialState(key));
  const scopeRef = useRef(key);
  const listRequestRef = useRef(0);
  const listAbortRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef(0);
  const detailAbortRef = useRef<AbortController | null>(null);
  const mutationRef = useRef<MutationOperation | null>(null);

  useEffect(() => {
    if (scopeRef.current === key) return;
    scopeRef.current = key;
    listRequestRef.current += 1;
    listAbortRef.current?.abort();
    listAbortRef.current = null;
    detailRequestRef.current += 1;
    detailAbortRef.current?.abort();
    detailAbortRef.current = null;
    mutationRef.current?.controller.abort();
    mutationRef.current = null;
    setState(initialState(key));
  }, [key]);

  useEffect(
    () => () => {
      listAbortRef.current?.abort();
      detailAbortRef.current?.abort();
      mutationRef.current?.controller.abort();
    },
    [],
  );

  const canLoad = options.profileId !== null && options.profileReady;

  const loadSessions = useCallback(async (): Promise<void> => {
    if (!canLoad) {
      setState((current) => ({...current, sessions: empty()}));
      return;
    }
    const request = ++listRequestRef.current;
    const requestScope = scopeRef.current;
    const controller = new AbortController();
    listAbortRef.current?.abort();
    listAbortRef.current = controller;
    setState((current) => ({
      ...current,
      sessions: {...current.sessions, phase: 'loading', error: null},
    }));
    try {
      const data = await api.fetchSessions(controller.signal);
      if (
        request !== listRequestRef.current ||
        controller.signal.aborted ||
        requestScope !== scopeRef.current
      ) {
        return;
      }
      setState((current) => ({
        ...current,
        sessions: {
          phase: data.items.length === 0 ? 'empty' : 'ready',
          data,
          error: null,
        },
      }));
    } catch (error) {
      if (
        request !== listRequestRef.current ||
        controller.signal.aborted ||
        requestScope !== scopeRef.current
      ) {
        return;
      }
      setState((current) => ({
        ...current,
        sessions: {
          phase: 'error',
          data: current.sessions.data,
          error: safeError(error),
        },
      }));
    }
  }, [api, canLoad]);

  const applyDetail = useCallback(
    (
      detail: TailoringSessionDetailResponse,
      requestScope: string,
      signal?: AbortSignal,
    ): boolean => {
      if (signal?.aborted || requestScope !== scopeRef.current) return false;
      setState((current) => ({
        ...current,
        selectedSessionId: detail.session.id,
        selectedVersionId: detail.selected_version?.id ?? null,
        detail: {phase: 'ready', data: detail, error: null},
        draft: detail.content,
        draftDirty: false,
        conflict: false,
        stream:
          isDurableCompletedDetail(detail) && mutationRef.current === null
            ? empty()
            : current.stream,
      }));
      return true;
    },
    [],
  );

  const fetchAndSelect = useCallback(
    async (
      sessionId: string,
      versionId?: string | null,
      signal?: AbortSignal,
      requestScope = scopeRef.current,
    ): Promise<TailoringSessionDetailResponse | null> => {
      const detail = await api.fetchSession(sessionId, versionId, signal);
      return applyDetail(detail, requestScope, signal) ? detail : null;
    },
    [api, applyDetail],
  );

  const fetchCompletedAndSelect = useCallback(
    async (
      sessionId: string,
      operation: MutationOperation,
    ): Promise<boolean> => {
      const detail = await api.fetchSession(
        sessionId,
        null,
        operation.controller.signal,
      );
      return (
        isDurableCompletedDetail(detail) &&
        mutationRef.current === operation &&
        applyDetail(
          detail,
          operation.scope,
          operation.controller.signal,
        )
      );
    },
    [api, applyDetail],
  );

  const openSession = useCallback(
    async (sessionId: string, versionId?: string | null): Promise<boolean> => {
      if (!canLoad) return false;
      const request = ++detailRequestRef.current;
      const requestScope = scopeRef.current;
      const controller = new AbortController();
      detailAbortRef.current?.abort();
      detailAbortRef.current = controller;
      setState((current) => ({
        ...current,
        detail: {...current.detail, phase: 'loading', error: null},
      }));
      try {
        const detail = await api.fetchSession(
          sessionId,
          versionId,
          controller.signal,
        );
        if (
          request !== detailRequestRef.current ||
          controller.signal.aborted ||
          requestScope !== scopeRef.current
        ) {
          return false;
        }
        return applyDetail(detail, requestScope, controller.signal);
      } catch (error) {
        if (
          controller.signal.aborted ||
          request !== detailRequestRef.current ||
          requestScope !== scopeRef.current
        ) {
          return false;
        }
        setState((current) => ({
          ...current,
          detail: {
            phase: 'error',
            data: current.detail.data,
            error: safeError(error),
          },
        }));
        return false;
      } finally {
        if (detailAbortRef.current === controller) {
          detailAbortRef.current = null;
        }
      }
    },
    [api, applyDetail, canLoad],
  );

  const recoverDisconnectedStream = useCallback(
    async (
      sessionId: string,
      operation: MutationOperation,
    ): Promise<StreamRecovery> => {
      try {
        const detail = await api.fetchSession(
          sessionId,
          null,
          operation.controller.signal,
        );
        if (
          operation.controller.signal.aborted ||
          operation.scope !== scopeRef.current ||
          mutationRef.current !== operation
        ) {
          return {kind: 'stale'};
        }
        const failed =
          detail.session.state === 'failed' || detail.latest_run?.state === 'failed';
        if (failed) {
          const code = asTailoringErrorCode(
            detail.latest_run?.error_code ?? detail.session.error_code,
          );
          return {
            kind: 'failed',
            error:
              code === null
                ? {
                    code: 'REQUEST_FAILED',
                    summary: 'CV tailoring request failed',
                  }
                : {code, summary: 'CV tailoring request failed'},
          };
        }
        if (isDurableCompletedDetail(detail)) {
          return {kind: 'completed', detail};
        }
        return {kind: 'pending'};
      } catch {
        return operation.controller.signal.aborted ||
          operation.scope !== scopeRef.current
          ? {kind: 'stale'}
          : {kind: 'pending'};
      }
    },
    [api],
  );

  const createSession = useCallback(
    async (body: CreateTailoringSessionRequest): Promise<string | null> => {
      if (!canLoad || mutationRef.current !== null) return null;
      const operation: MutationOperation = {
        scope: scopeRef.current,
        controller: new AbortController(),
      };
      mutationRef.current = operation;
      let pendingSessionId: string | null = null;
      let completed = false;
      let terminalOutcome: TailoringMutationOutcome | null = null;
      let terminalError: TailoringSafeError | null = null;
      let disconnected = false;
      setState((current) => ({
        ...current,
        stream: {phase: 'loading', data: null, error: null},
        lastOutcome: null,
        lastOutcomeSource: null,
      }));
      try {
        await api.streamCreate(
          body,
          {
            onSessionId: (id) => {
              pendingSessionId = id;
            },
            onEvent: (event) => {
              if (event.event === 'run_completed') {
                completed = true;
                terminalOutcome = event.payload.outcome ?? null;
              }
              terminalError = streamError(event) ?? terminalError;
            },
            onDisconnected: () => {
              disconnected = true;
              terminalError = {
                code: 'STREAM_DISCONNECTED',
                summary: 'CV tailoring stream disconnected',
              };
            },
          },
          operation.controller.signal,
        );
        if (
          operation.controller.signal.aborted ||
          operation.scope !== scopeRef.current ||
          mutationRef.current !== operation
        ) {
          return null;
        }
        if (disconnected && pendingSessionId !== null) {
          const recovery = await recoverDisconnectedStream(
            pendingSessionId,
            operation,
          );
          if (recovery.kind === 'stale') return null;
          if (recovery.kind === 'completed') {
            if (
              !applyDetail(
                recovery.detail,
                operation.scope,
                operation.controller.signal,
              )
            ) {
              return null;
            }
            setState((current) => ({
              ...current,
              stream: {phase: 'ready', data: null, error: null},
              lastOutcome: terminalOutcome ?? 'version_created',
              lastOutcomeSource: 'ai',
            }));
            await loadSessions();
            return pendingSessionId;
          }
          if (recovery.kind === 'failed') {
            setState((current) => ({
              ...current,
              stream: {phase: 'error', data: null, error: recovery.error},
            }));
            return null;
          }
        }
        if (!completed || pendingSessionId === null || terminalError !== null) {
          setState((current) => ({
            ...current,
            stream: {
              phase:
                terminalError?.code === 'STREAM_DISCONNECTED'
                  ? 'disconnected'
                  : 'error',
              data: null,
              error:
                terminalError ?? {
                  code: 'REQUEST_FAILED',
                  summary: 'CV tailoring did not complete',
                },
            },
          }));
          return null;
        }
        const selectedId: string = pendingSessionId;
        if (!(await fetchCompletedAndSelect(selectedId, operation))) {
          if (
            !operation.controller.signal.aborted &&
            operation.scope === scopeRef.current &&
            mutationRef.current === operation
          ) {
            setState((current) => ({
              ...current,
              stream: {
                phase: 'error',
                data: null,
                error: {
                  code: 'REQUEST_FAILED',
                  summary: 'CV tailoring did not complete',
                },
              },
            }));
          }
          return null;
        }
        setState((current) => ({
          ...current,
          stream: {phase: 'ready', data: null, error: null},
          lastOutcome: terminalOutcome ?? 'version_created',
          lastOutcomeSource: 'ai',
        }));
        await loadSessions();
        return selectedId;
      } catch (error) {
        if (
          !operation.controller.signal.aborted &&
          operation.scope === scopeRef.current &&
          mutationRef.current === operation
        ) {
          setState((current) => ({
            ...current,
            stream: {phase: 'error', data: null, error: safeError(error)},
          }));
        }
        return null;
      } finally {
        if (mutationRef.current === operation) mutationRef.current = null;
      }
    },
    [
      api,
      applyDetail,
      canLoad,
      fetchCompletedAndSelect,
      loadSessions,
      recoverDisconnectedStream,
    ],
  );

  const createAiVersion = useCallback(
    async (
      sessionId: string,
      body: CreateTailoringAiVersionRequest,
    ): Promise<boolean> => {
      if (!canLoad || mutationRef.current !== null) return false;
      const operation: MutationOperation = {
        scope: scopeRef.current,
        controller: new AbortController(),
      };
      mutationRef.current = operation;
      let completed = false;
      let terminalOutcome: TailoringMutationOutcome | null = null;
      let terminalVersionId: string | null = null;
      let terminalVersionNumber: number | null = null;
      let terminalError: TailoringSafeError | null = null;
      let disconnected = false;
      const knownParentId = body.parent_version_id;
      const knownParentNumber = state.detail.data?.selected_version?.version_number ?? null;
      setState((current) => ({
        ...current,
        stream: {phase: 'loading', data: null, error: null},
        lastOutcome: null,
        lastOutcomeSource: null,
      }));
      try {
        await api.streamAiVersion(
          sessionId,
          body,
          {
            onEvent: (event) => {
              if (event.event === 'run_completed') {
                completed = true;
                terminalOutcome = event.payload.outcome ?? null;
                terminalVersionId = event.payload.version_id ?? null;
                terminalVersionNumber = event.payload.version_number ?? null;
              }
              terminalError = streamError(event) ?? terminalError;
            },
            onDisconnected: () => {
              disconnected = true;
              terminalError = {
                code: 'STREAM_DISCONNECTED',
                summary: 'CV tailoring stream disconnected',
              };
            },
          },
          operation.controller.signal,
        );
        if (
          operation.controller.signal.aborted ||
          operation.scope !== scopeRef.current ||
          mutationRef.current !== operation
        ) {
          return false;
        }
        if (disconnected) {
          const recovery = await recoverDisconnectedStream(sessionId, operation);
          if (recovery.kind === 'stale') return false;
          if (recovery.kind === 'completed') {
            const recoveredNoChange =
              knownParentId !== null &&
              knownParentNumber !== null &&
              recovery.detail.selected_version?.id === knownParentId &&
              recovery.detail.selected_version.version_number === knownParentNumber &&
              recovery.detail.session.latest_version_number === knownParentNumber;
            if (
              !applyDetail(
                recovery.detail,
                operation.scope,
                operation.controller.signal,
              )
            ) {
              return false;
            }
            setState((current) => ({
              ...current,
              stream: {phase: 'ready', data: null, error: null},
              lastOutcome: recoveredNoChange ? 'no_change' : 'version_created',
              lastOutcomeSource: 'ai',
            }));
            await loadSessions();
            return true;
          }
          if (recovery.kind === 'failed') {
            setState((current) => ({
              ...current,
              stream: {phase: 'error', data: null, error: recovery.error},
            }));
            return false;
          }
        }
        if (!completed || terminalError !== null) {
          setState((current) => ({
            ...current,
            stream: {
              phase:
                terminalError?.code === 'STREAM_DISCONNECTED'
                  ? 'disconnected'
                  : 'error',
              data: null,
              error:
                terminalError ?? {
                  code: 'REQUEST_FAILED',
                  summary: 'CV tailoring did not complete',
                },
            },
          }));
          return false;
        }
        if (terminalOutcome === 'no_change') {
          if (
            terminalVersionId !== knownParentId ||
            terminalVersionNumber !== knownParentNumber
          ) {
            setState((current) => ({
              ...current,
              stream: {
                phase: 'error',
                data: null,
                error: {code: 'REQUEST_FAILED', summary: 'CV tailoring response did not match its parent version'},
              },
            }));
            return false;
          }
          setState((current) => ({
            ...current,
            stream: {phase: 'ready', data: null, error: null},
            lastOutcome: 'no_change',
            lastOutcomeSource: 'ai',
          }));
          return true;
        }
        if (!(await fetchCompletedAndSelect(sessionId, operation))) {
          if (
            !operation.controller.signal.aborted &&
            operation.scope === scopeRef.current &&
            mutationRef.current === operation
          ) {
            setState((current) => ({
              ...current,
              stream: {
                phase: 'error',
                data: null,
                error: {
                  code: 'REQUEST_FAILED',
                  summary: 'CV tailoring did not complete',
                },
              },
            }));
          }
          return false;
        }
        setState((current) => ({
          ...current,
          stream: {phase: 'ready', data: null, error: null},
          lastOutcome: terminalOutcome ?? 'version_created',
          lastOutcomeSource: 'ai',
        }));
        await loadSessions();
        return true;
      } catch (error) {
        if (
          !operation.controller.signal.aborted &&
          operation.scope === scopeRef.current &&
          mutationRef.current === operation
        ) {
          setState((current) => ({
            ...current,
            stream: {phase: 'error', data: null, error: safeError(error)},
          }));
        }
        return false;
      } finally {
        if (mutationRef.current === operation) mutationRef.current = null;
      }
    },
    [
      api,
      applyDetail,
      canLoad,
      fetchCompletedAndSelect,
      loadSessions,
      recoverDisconnectedStream,
      state.detail.data?.selected_version?.version_number,
    ],
  );

  const setDraft = useCallback((draft: TailoredCVContent) => {
    setState((current) => ({
      ...current,
      draft,
      draftDirty: true,
      lastOutcome: null,
      lastOutcomeSource: null,
    }));
  }, []);

  const saveManualVersion = useCallback(async (): Promise<boolean> => {
    if (
      !canLoad ||
      mutationRef.current !== null ||
      state.selectedSessionId === null ||
      state.selectedVersionId === null ||
      state.draft === null
    ) {
      return false;
    }
    const operation: MutationOperation = {
      scope: scopeRef.current,
      controller: new AbortController(),
    };
    mutationRef.current = operation;
    setState((current) => ({
      ...current,
      stream: {phase: 'loading', data: null, error: null},
      lastOutcome: null,
      lastOutcomeSource: null,
    }));
    try {
      const created = await api.createManualVersion(state.selectedSessionId, {
        parent_version_id: state.selectedVersionId,
        content: state.draft,
      }, operation.controller.signal);
      if (
        operation.controller.signal.aborted ||
        operation.scope !== scopeRef.current ||
        mutationRef.current !== operation
      ) {
        return false;
      }
      if (created.outcome === 'no_change') {
        setState((current) => ({
          ...current,
          draftDirty: false,
          conflict: false,
          detail: {...current.detail, error: null},
          stream: {phase: 'ready', data: null, error: null},
          lastOutcome: 'no_change',
          lastOutcomeSource: 'manual',
        }));
        return true;
      }
      if (
        (await fetchAndSelect(
          state.selectedSessionId,
          created.version_id,
          operation.controller.signal,
          operation.scope,
        )) === null
      ) {
        return false;
      }
      await loadSessions();
      setState((current) => ({
        ...current,
        stream: {phase: 'ready', data: null, error: null},
        lastOutcome: 'version_created',
        lastOutcomeSource: 'manual',
      }));
      return true;
    } catch (error) {
      if (
        operation.controller.signal.aborted ||
        operation.scope !== scopeRef.current ||
        mutationRef.current !== operation
      ) {
        return false;
      }
      const mapped = safeError(error);
      setState((current) => ({
        ...current,
        conflict: mapped.code === 'TAILORING_PARENT_CONFLICT',
        detail: {
          phase: 'error',
          data: current.detail.data,
          error: mapped,
        },
        stream: {phase: 'error', data: null, error: mapped},
      }));
      return false;
    } finally {
      if (mutationRef.current === operation) mutationRef.current = null;
    }
  }, [api, canLoad, fetchAndSelect, loadSessions, state]);

  const selectVersion = useCallback(
    async (versionId: string, discardUnsaved = false): Promise<boolean> => {
      if (state.selectedSessionId === null) return false;
      if (state.draftDirty && !discardUnsaved) return false;
      return openSession(state.selectedSessionId, versionId);
    },
    [openSession, state.draftDirty, state.selectedSessionId],
  );

  const deleteSession = useCallback(
    async (sessionId: string): Promise<boolean> => {
      if (mutationRef.current !== null) return false;
      const operation: MutationOperation = {
        scope: scopeRef.current,
        controller: new AbortController(),
      };
      mutationRef.current = operation;
      try {
        await api.deleteSession(sessionId, operation.controller.signal);
        if (
          operation.controller.signal.aborted ||
          operation.scope !== scopeRef.current ||
          mutationRef.current !== operation
        ) {
          return false;
        }
        setState((current) =>
          current.selectedSessionId === sessionId
            ? initialState(current.profileScopeKey)
            : current,
        );
        await loadSessions();
        return true;
      } catch (error) {
        if (
          operation.controller.signal.aborted ||
          operation.scope !== scopeRef.current ||
          mutationRef.current !== operation
        ) {
          return false;
        }
        setState((current) => ({
          ...current,
          detail: {
            phase: 'error',
            data: current.detail.data,
            error: safeError(error),
          },
        }));
        return false;
      } finally {
        if (mutationRef.current === operation) mutationRef.current = null;
      }
    },
    [api, loadSessions],
  );

  return {
    state,
    loadSessions,
    openSession,
    createSession,
    createAiVersion,
    setDraft,
    saveManualVersion,
    selectVersion,
    deleteSession,
  };
}

export type CvTailoringController = ReturnType<typeof useCvTailoringState>;

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';

import {ChatApiError} from '../../lib/api/chat';
import type {SseEvent} from '../chat/types';
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
};

export type UseCvTailoringOptions = {
  readonly profileId: string | null;
  readonly profileReady: boolean;
  readonly api?: Partial<CvTailoringApi>;
};

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

function streamError(event: SseEvent): TailoringSafeError | null {
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

export function useCvTailoringState(options: UseCvTailoringOptions) {
  const key = scopeKey(options.profileId, options.profileReady);
  const api = useMemo<CvTailoringApi>(
    () => ({...defaultCvTailoringApi, ...options.api}),
    [options.api],
  );
  const [state, setState] = useState<CvTailoringState>(() => initialState(key));
  const scopeRef = useRef(key);
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mutationRef = useRef(false);

  useEffect(() => {
    if (scopeRef.current === key) return;
    scopeRef.current = key;
    requestRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    mutationRef.current = false;
    setState(initialState(key));
  }, [key]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const canLoad = options.profileId !== null && options.profileReady;

  const loadSessions = useCallback(async (): Promise<void> => {
    if (!canLoad) {
      setState((current) => ({...current, sessions: empty()}));
      return;
    }
    const request = ++requestRef.current;
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    setState((current) => ({
      ...current,
      sessions: {...current.sessions, phase: 'loading', error: null},
    }));
    try {
      const data = await api.fetchSessions(controller.signal);
      if (request !== requestRef.current || controller.signal.aborted) return;
      setState((current) => ({
        ...current,
        sessions: {
          phase: data.items.length === 0 ? 'empty' : 'ready',
          data,
          error: null,
        },
      }));
    } catch (error) {
      if (request !== requestRef.current || controller.signal.aborted) return;
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

  const fetchAndSelect = useCallback(
    async (
      sessionId: string,
      versionId?: string | null,
      signal?: AbortSignal,
    ): Promise<TailoringSessionDetailResponse | null> => {
      const requestScope = scopeRef.current;
      const detail = await api.fetchSession(sessionId, versionId, signal);
      if (signal?.aborted || requestScope !== scopeRef.current) {
        return null;
      }
      setState((current) => ({
        ...current,
        selectedSessionId: detail.session.id,
        selectedVersionId: detail.selected_version?.id ?? null,
        detail: {phase: 'ready', data: detail, error: null},
        draft: detail.content,
        draftDirty: false,
        conflict: false,
      }));
      return detail;
    },
    [api],
  );

  const openSession = useCallback(
    async (sessionId: string, versionId?: string | null): Promise<boolean> => {
      if (!canLoad) return false;
      const controller = new AbortController();
      setState((current) => ({
        ...current,
        detail: {...current.detail, phase: 'loading', error: null},
      }));
      try {
        return (await fetchAndSelect(sessionId, versionId, controller.signal)) !== null;
      } catch (error) {
        if (controller.signal.aborted) return false;
        setState((current) => ({
          ...current,
          detail: {
            phase: 'error',
            data: current.detail.data,
            error: safeError(error),
          },
        }));
        return false;
      }
    },
    [canLoad, fetchAndSelect],
  );

  const recoverDisconnectedStream = useCallback(
    async (sessionId: string, controller: AbortController): Promise<boolean> => {
      try {
        return (await fetchAndSelect(sessionId, null, controller.signal)) !== null;
      } catch {
        return false;
      }
    },
    [fetchAndSelect],
  );

  const createSession = useCallback(
    async (body: CreateTailoringSessionRequest): Promise<string | null> => {
      if (!canLoad || mutationRef.current) return null;
      mutationRef.current = true;
      let pendingSessionId: string | null = null;
      let completed = false;
      let terminalError: TailoringSafeError | null = null;
      let disconnected = false;
      const controller = new AbortController();
      setState((current) => ({
        ...current,
        stream: {phase: 'loading', data: null, error: null},
      }));
      try {
        await api.streamCreate(
          body,
          {
            onSessionId: (id) => {
              pendingSessionId = id;
            },
            onEvent: (event) => {
              if (event.event === 'run_completed') completed = true;
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
          controller.signal,
        );
        if (
          disconnected &&
          pendingSessionId !== null &&
          await recoverDisconnectedStream(pendingSessionId, controller)
        ) {
          setState((current) => ({
            ...current,
            stream: {phase: 'ready', data: null, error: null},
          }));
          await loadSessions();
          return pendingSessionId;
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
        if ((await fetchAndSelect(selectedId, null, controller.signal)) === null) {
          return null;
        }
        setState((current) => ({
          ...current,
          stream: {phase: 'ready', data: null, error: null},
        }));
        await loadSessions();
        return selectedId;
      } catch (error) {
        if (!controller.signal.aborted) {
          setState((current) => ({
            ...current,
            stream: {phase: 'error', data: null, error: safeError(error)},
          }));
        }
        return null;
      } finally {
        mutationRef.current = false;
      }
    },
    [api, canLoad, fetchAndSelect, loadSessions, recoverDisconnectedStream],
  );

  const createAiVersion = useCallback(
    async (
      sessionId: string,
      body: CreateTailoringAiVersionRequest,
    ): Promise<boolean> => {
      if (!canLoad || mutationRef.current) return false;
      mutationRef.current = true;
      let completed = false;
      let terminalError: TailoringSafeError | null = null;
      let disconnected = false;
      const controller = new AbortController();
      setState((current) => ({
        ...current,
        stream: {phase: 'loading', data: null, error: null},
      }));
      try {
        await api.streamAiVersion(
          sessionId,
          body,
          {
            onEvent: (event) => {
              if (event.event === 'run_completed') completed = true;
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
          controller.signal,
        );
        if (
          disconnected &&
          await recoverDisconnectedStream(sessionId, controller)
        ) {
          setState((current) => ({
            ...current,
            stream: {phase: 'ready', data: null, error: null},
          }));
          await loadSessions();
          return true;
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
        if ((await fetchAndSelect(sessionId, null, controller.signal)) === null) {
          return false;
        }
        setState((current) => ({
          ...current,
          stream: {phase: 'ready', data: null, error: null},
        }));
        await loadSessions();
        return true;
      } catch (error) {
        if (!controller.signal.aborted) {
          setState((current) => ({
            ...current,
            stream: {phase: 'error', data: null, error: safeError(error)},
          }));
        }
        return false;
      } finally {
        mutationRef.current = false;
      }
    },
    [api, canLoad, fetchAndSelect, loadSessions, recoverDisconnectedStream],
  );

  const setDraft = useCallback((draft: TailoredCVContent) => {
    setState((current) => ({...current, draft, draftDirty: true}));
  }, []);

  const saveManualVersion = useCallback(async (): Promise<boolean> => {
    if (
      !canLoad ||
      mutationRef.current ||
      state.selectedSessionId === null ||
      state.selectedVersionId === null ||
      state.draft === null
    ) {
      return false;
    }
    mutationRef.current = true;
    try {
      const created = await api.createManualVersion(state.selectedSessionId, {
        parent_version_id: state.selectedVersionId,
        content: state.draft,
      });
      if ((await fetchAndSelect(
        state.selectedSessionId,
        created.version_id,
      )) === null) {
        return false;
      }
      await loadSessions();
      return true;
    } catch (error) {
      const mapped = safeError(error);
      setState((current) => ({
        ...current,
        conflict: mapped.code === 'TAILORING_PARENT_CONFLICT',
        detail: {
          phase: 'error',
          data: current.detail.data,
          error: mapped,
        },
      }));
      return false;
    } finally {
      mutationRef.current = false;
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
      if (mutationRef.current) return false;
      mutationRef.current = true;
      try {
        await api.deleteSession(sessionId);
        setState((current) =>
          current.selectedSessionId === sessionId
            ? initialState(current.profileScopeKey)
            : current,
        );
        await loadSessions();
        return true;
      } catch (error) {
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
        mutationRef.current = false;
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

import {act, renderHook, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {useCvTailoringState} from '../features/cv-tailoring/state';
import type {TailoringSessionDetailResponse} from '../features/cv-tailoring/types';
import {ChatApiError} from '../lib/api/chat';
import appSource from '../app/App.tsx?raw';
import observabilitySource from '../features/observability/ObservabilitySidebar.tsx?raw';

const PROFILE_ID = '22222222-2222-4222-8222-222222222222';
const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const OTHER_SESSION_ID = '33333333-3333-4333-8333-333333333333';
const VERSION_ID = '44444444-4444-4444-8444-444444444444';
const RUN_ID = '55555555-5555-4555-8555-555555555555';
const NOW = '2026-07-26T00:00:00Z';

function durableDetail(
  sessionId = SESSION_ID,
  options: {
    sessionState?: 'generating' | 'ready' | 'failed' | 'deleting';
    runState?: 'running' | 'interrupted' | 'completed' | 'failed';
    errorCode?: string | null;
  } = {},
): TailoringSessionDetailResponse {
  const sessionState = options.sessionState ?? 'ready';
  const runState = options.runState ?? 'completed';
  const errorCode = options.errorCode ?? null;
  const hasVersion = sessionState === 'ready';
  const version = hasVersion
    ? {
        id: VERSION_ID,
        version_number: 1,
        parent_version_id: null,
        created_by: 'ai' as const,
        page_count: 1,
        page_warning: null,
        created_at: NOW,
      }
    : null;
  return {
    session: {
      id: sessionId,
      profile_id: PROFILE_ID,
      job_label: null,
      instruction: 'Focus',
      template_version: 'latex-cv-v1',
      state: sessionState,
      currentness: 'current',
      latest_version_number: hasVersion ? 1 : 0,
      error_code: errorCode,
      created_at: NOW,
      updated_at: NOW,
    },
    versions: version ? [version] : [],
    selected_version: version,
    content: version
      ? {
          header: {
            full_name: 'Synthetic Candidate',
            location: null,
            phone: null,
            email: null,
            github_url: null,
          },
          sections: [
            {
              id: 'summary',
              ordinal: 0,
              heading: 'Summary',
              kind: 'summary',
              items: [],
            },
          ],
        }
      : null,
    evidence: [],
    latest_run: {
      id: RUN_ID,
      state: runState,
      error_code: errorCode,
      activities: [],
    },
    source_available: hasVersion,
    pdf_available: hasVersion,
  };
}

describe('CV tailoring state owner', () => {
  it('keeps the sole production saved-JD hook call in App', () => {
    expect(appSource.match(/useSavedJobsState\s*\(/g)).toHaveLength(1);
    expect(observabilitySource).not.toMatch(/useSavedJobsState\s*\(/);
  });
  it('drops server data when profile scope changes', async () => {
    const fetchSessions = vi.fn().mockResolvedValue({items: []});
    const {result, rerender} = renderHook(
      ({profileId}) =>
        useCvTailoringState({
          profileId,
          profileReady: true,
          api: {fetchSessions},
        }),
      {initialProps: {profileId: PROFILE_ID}},
    );
    await act(async () => result.current.loadSessions());
    await waitFor(() => expect(result.current.state.sessions.phase).toBe('empty'));
    rerender({profileId: '33333333-3333-4333-8333-333333333333'});
    expect(result.current.state.selectedSessionId).toBeNull();
    expect(result.current.state.detail.data).toBeNull();
  });

  it('drops a detail response that resolves after the profile scope changes', async () => {
    let resolveDetail: ((detail: never) => void) | null = null;
    const fetchSession = vi.fn(
      () =>
        new Promise<never>((resolve) => {
          resolveDetail = resolve;
        }),
    );
    const {result, rerender} = renderHook(
      ({profileId}) =>
        useCvTailoringState({
          profileId,
          profileReady: true,
          api: {fetchSession},
        }),
      {initialProps: {profileId: PROFILE_ID}},
    );

    let opening: Promise<boolean>;
    act(() => {
      opening = result.current.openSession(SESSION_ID);
    });
    rerender({profileId: '33333333-3333-4333-8333-333333333333'});
    await act(async () => {
      resolveDetail?.({
        session: {id: SESSION_ID},
        selected_version: null,
        content: null,
      } as never);
      await opening!;
    });

    expect(result.current.state.profileScopeKey).toContain('33333333');
    expect(result.current.state.selectedSessionId).toBeNull();
    expect(result.current.state.detail.data).toBeNull();
  });

  it('maps an unknown ChatApiError code to REQUEST_FAILED', async () => {
    const fetchSessions = vi
      .fn()
      .mockRejectedValue(new ChatApiError(500, 'UNSAFE_SERVER_CODE', 'unsafe'));
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {fetchSessions},
      }),
    );

    await act(async () => result.current.loadSessions());

    expect(result.current.state.sessions.error).toEqual({
      code: 'REQUEST_FAILED',
      summary: 'CV tailoring request failed',
    });
  });

  it('recovers a disconnected create stream from durable session detail', async () => {
    const streamCreate = vi.fn(async (_body, callbacks) => {
      callbacks.onSessionId(SESSION_ID);
      callbacks.onDisconnected?.();
    });
    const fetchSession = vi.fn().mockResolvedValue(durableDetail());
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {streamCreate, fetchSession},
      }),
    );

    let created: string | null = null;
    await act(async () => {
      created = await result.current.createSession({job_id: null, instruction: 'Focus'});
    });

    expect(created).toBe(SESSION_ID);
    expect(fetchSession).toHaveBeenCalledWith(SESSION_ID, null, expect.any(AbortSignal));
    expect(result.current.state.stream.phase).toBe('ready');
  });

  it('does not select a still-running session after a disconnected create stream', async () => {
    const streamCreate = vi.fn(async (_body, callbacks) => {
      callbacks.onSessionId(SESSION_ID);
      callbacks.onDisconnected?.();
    });
    const fetchSession = vi
      .fn()
      .mockResolvedValue(
        durableDetail(SESSION_ID, {
          sessionState: 'generating',
          runState: 'running',
        }),
      );
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {streamCreate, fetchSession},
      }),
    );

    let created: string | null = SESSION_ID;
    await act(async () => {
      created = await result.current.createSession({
        job_id: null,
        instruction: 'Focus',
      });
    });

    expect(created).toBeNull();
    expect(result.current.state.selectedSessionId).toBeNull();
    expect(result.current.state.stream.phase).toBe('disconnected');
  });

  it('requires durable completed detail after a run_completed event', async () => {
    const streamCreate = vi.fn(async (_body, callbacks) => {
      callbacks.onSessionId(SESSION_ID);
      callbacks.onEvent({
        event: 'run_completed',
        run_id: RUN_ID,
        payload: {state: 'completed'},
      });
    });
    const fetchSession = vi
      .fn()
      .mockResolvedValue(
        durableDetail(SESSION_ID, {
          sessionState: 'generating',
          runState: 'running',
        }),
      );
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {streamCreate, fetchSession},
      }),
    );

    let created: string | null = SESSION_ID;
    await act(async () => {
      created = await result.current.createSession({
        job_id: null,
        instruction: 'Focus',
      });
    });

    expect(created).toBeNull();
    expect(result.current.state.selectedSessionId).toBeNull();
    expect(result.current.state.stream.phase).toBe('error');
  });

  it('keeps the latest same-profile session selection when responses resolve out of order', async () => {
    const resolvers = new Map<
      string,
      (detail: TailoringSessionDetailResponse) => void
    >();
    const fetchSession = vi.fn(
      (sessionId: string) =>
        new Promise<TailoringSessionDetailResponse>((resolve) => {
          resolvers.set(sessionId, resolve);
        }),
    );
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {fetchSession},
      }),
    );

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.openSession(SESSION_ID);
      second = result.current.openSession(OTHER_SESSION_ID);
    });
    await act(async () => {
      resolvers.get(OTHER_SESSION_ID)?.(durableDetail(OTHER_SESSION_ID));
      await second;
      resolvers.get(SESSION_ID)?.(durableDetail(SESSION_ID));
      await first;
    });

    expect(result.current.state.selectedSessionId).toBe(OTHER_SESSION_ID);
  });

  it('drops a completed create mutation after the profile scope changes', async () => {
    let finishStream: (() => void) | null = null;
    const streamCreate = vi.fn(
      async (_body, callbacks) =>
        new Promise<void>((resolve) => {
          callbacks.onSessionId(SESSION_ID);
          finishStream = () => {
            callbacks.onEvent({
              event: 'run_completed',
              run_id: RUN_ID,
              payload: {state: 'completed'},
            });
            resolve();
          };
        }),
    );
    const fetchSession = vi.fn().mockResolvedValue(durableDetail());
    const {result, rerender} = renderHook(
      ({profileId}) =>
        useCvTailoringState({
          profileId,
          profileReady: true,
          api: {streamCreate, fetchSession},
        }),
      {initialProps: {profileId: PROFILE_ID}},
    );

    let creating!: Promise<string | null>;
    act(() => {
      creating = result.current.createSession({
        job_id: null,
        instruction: 'Focus',
      });
    });
    rerender({profileId: '66666666-6666-4666-8666-666666666666'});
    await waitFor(() =>
      expect(result.current.state.profileScopeKey).toContain(
        '66666666-6666-4666-8666-666666666666',
      ),
    );
    await act(async () => {
      finishStream?.();
      await creating;
    });

    expect(fetchSession).not.toHaveBeenCalled();
    expect(result.current.state.selectedSessionId).toBeNull();
    expect(result.current.state.stream.phase).toBe('idle');
  });

  it('preserves the local draft when durable AI recovery reports failure', async () => {
    const ready = durableDetail();
    const failed: TailoringSessionDetailResponse = {
      ...ready,
      session: {
        ...ready.session,
        state: 'failed',
        error_code: 'TAILORING_GROUNDING_FAILED',
      },
      latest_run: {
        ...ready.latest_run!,
        state: 'failed',
        error_code: 'TAILORING_GROUNDING_FAILED',
      },
    };
    const fetchSession = vi
      .fn()
      .mockResolvedValueOnce(ready)
      .mockResolvedValueOnce(failed);
    const streamAiVersion = vi.fn(async (_sessionId, _body, callbacks) => {
      callbacks.onDisconnected?.();
    });
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {fetchSession, streamAiVersion},
      }),
    );
    await act(async () => {
      await result.current.openSession(SESSION_ID);
    });
    const draft = {
      ...ready.content!,
      header: {...ready.content!.header, full_name: 'Unsaved local draft'},
    };
    act(() => result.current.setDraft(draft));

    let saved = true;
    await act(async () => {
      saved = await result.current.createAiVersion(SESSION_ID, {
        parent_version_id: VERSION_ID,
        instruction: 'Focus',
        target_section_ids: ['summary'],
      });
    });

    expect(saved).toBe(false);
    expect(result.current.state.draft).toBe(draft);
    expect(result.current.state.draftDirty).toBe(true);
    expect(result.current.state.stream.error?.code).toBe(
      'TAILORING_GROUNDING_FAILED',
    );
  });

  it('does not select a session when initial stream fails', async () => {
    const streamCreate = vi.fn(async (_body, callbacks) => {
      callbacks.onSessionId(SESSION_ID);
      callbacks.onEvent({
        event: 'run_failed',
        run_id: '44444444-4444-4444-8444-444444444444',
        payload: {
          state: 'failed',
          error_code: 'TAILORING_GROUNDING_FAILED',
          summary: 'Tailored content is not source-supported',
        },
      });
    });
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {streamCreate},
      }),
    );
    await act(async () => {
      await result.current.createSession({job_id: null, instruction: 'Focus'});
    });
    expect(result.current.state.selectedSessionId).toBeNull();
    expect(result.current.state.stream.phase).toBe('error');
  });

  it('clears a prior stream error when opening a durable ready session', async () => {
    const streamCreate = vi.fn(async (_body, callbacks) => {
      callbacks.onSessionId(SESSION_ID);
      callbacks.onEvent({
        event: 'run_failed',
        run_id: RUN_ID,
        payload: {
          state: 'failed',
          error_code: 'TAILORING_GROUNDING_FAILED',
          summary: 'Tailored content is not source-supported',
        },
      });
    });
    const fetchSession = vi
      .fn()
      .mockResolvedValue(durableDetail(OTHER_SESSION_ID));
    const {result} = renderHook(() =>
      useCvTailoringState({
        profileId: PROFILE_ID,
        profileReady: true,
        api: {streamCreate, fetchSession},
      }),
    );

    await act(async () => {
      await result.current.createSession({job_id: null, instruction: 'Focus'});
    });
    expect(result.current.state.stream.error?.code).toBe(
      'TAILORING_GROUNDING_FAILED',
    );

    await act(async () => {
      expect(await result.current.openSession(OTHER_SESSION_ID)).toBe(true);
    });

    expect(result.current.state.selectedSessionId).toBe(OTHER_SESSION_ID);
    expect(result.current.state.stream.error).toBeNull();
  });
});

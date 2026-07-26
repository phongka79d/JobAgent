import {act, renderHook, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {useCvTailoringState} from '../features/cv-tailoring/state';
import {ChatApiError} from '../lib/api/chat';
import appSource from '../app/App.tsx?raw';
import observabilitySource from '../features/observability/ObservabilitySidebar.tsx?raw';

const PROFILE_ID = '22222222-2222-4222-8222-222222222222';
const SESSION_ID = '11111111-1111-4111-8111-111111111111';

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
    const fetchSession = vi.fn().mockResolvedValue({
      session: {id: SESSION_ID},
      selected_version: null,
      content: null,
    });
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
});

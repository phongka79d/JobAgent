import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  App,
  freshTailoringRequest,
  reloadLatestTailoring,
  selectedScorableJobId,
} from './App';
import type {
  ConversationSummary,
  ProfileListItem,
  ProfileListResponse,
} from '../features/profile/conversationTypes';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return {promise, resolve, reject};
}

function appProfile(id: string, isActive: boolean): ProfileListItem {
  return {
    id,
    display_name: id,
    cv_filename: `${id}.pdf`,
    attachment_state: 'active',
    location: null,
    skill_tags: [],
    skill_count: 0,
    extraction_version: 'v1',
    source_hash: id,
    state: 'ready',
    setup_status: null,
    is_active: isActive,
    created_at: '2026-07-28T00:00:00Z',
    updated_at: '2026-07-28T00:00:00Z',
    last_opened_at: '2026-07-28T00:00:00Z',
  };
}

function appConversation(id: string, profileId: string): ConversationSummary {
  return {
    id,
    profile_id: profileId,
    title: id,
    created_at: '2026-07-28T00:00:00Z',
    updated_at: '2026-07-28T00:00:00Z',
    last_opened_at: '2026-07-28T00:00:00Z',
    is_selected: true,
  };
}

describe('App foundation shell', () => {
  it('retains only a selected scorable Job for fresh tailoring recovery', () => {
    const job = {
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Synthetic job',
      company: 'Synthetic Co',
      processing_status: 'processed' as const,
      jd_quality: 'full' as const,
      source_type: 'text' as const,
      source_url: null,
      created_at: '2026-07-26T00:00:00Z',
      updated_at: '2026-07-26T00:00:00Z',
      evaluation_state: 'current' as const,
      latest_score: null,
    };
    expect(
      selectedScorableJobId({
        selectedJobId: job.id,
        list: {
          phase: 'ready',
          data: {items: [job], next_cursor: null},
          error: null,
          loaded: true,
        },
      }),
    ).toBe(job.id);
    expect(
      selectedScorableJobId({
        selectedJobId: job.id,
        list: {
          phase: 'ready',
          data: {
            items: [{...job, jd_quality: 'unscorable'}],
            next_cursor: null,
          },
          error: null,
          loaded: true,
        },
      }),
    ).toBeNull();

    const selectedState = {
      selectedJobId: job.id,
      list: {
        phase: 'ready' as const,
        data: {items: [job], next_cursor: null},
        error: null,
        loaded: true,
      },
    };
    expect(freshTailoringRequest(selectedState, '   ')).toEqual({
      job_id: job.id,
      instruction: '',
    });
    expect(
      freshTailoringRequest(
        {
          ...selectedState,
          list: {
            ...selectedState.list,
            data: {
              items: [{...job, jd_quality: 'unscorable' as const}],
              next_cursor: null,
            },
          },
        },
        '  Focus on evidence  ',
      ),
    ).toEqual({job_id: null, instruction: 'Focus on evidence'});
    expect(
      freshTailoringRequest(
        {
          ...selectedState,
          list: {
            ...selectedState.list,
            data: {
              items: [{...job, jd_quality: 'unscorable' as const}],
              next_cursor: null,
            },
          },
        },
        '   ',
      ),
    ).toBeNull();
  });

  it('reloads the latest parent while preserving the local tailoring draft', async () => {
    const draft = {
      header: {
        full_name: 'Synthetic Candidate',
        location: null,
        phone: null,
        email: null,
        github_url: null,
      },
      sections: [],
    };
    const openSession = vi.fn().mockResolvedValue(true);
    const setDraft = vi.fn();

    expect(
      await reloadLatestTailoring({
        state: {
          selectedSessionId: '11111111-1111-4111-8111-111111111111',
          draft,
        },
        openSession,
        setDraft,
      }),
    ).toBe(true);
    expect(openSession).toHaveBeenCalledWith(
      '11111111-1111-4111-8111-111111111111',
    );
    expect(setDraft).toHaveBeenCalledWith(draft);
  });

  it('renders AppShell with CV sidebar and chat page', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/profiles')) {
        return new Response(
          JSON.stringify({items: [], active_profile_id: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.includes('/api/profile') && !url.includes('/cv')) {
        return new Response(
          JSON.stringify({
            present: false,
            profile: null,
            preferences: null,
            active_attachment: null,
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      return new Response(JSON.stringify({items: [], next_cursor: null}), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      });
    });

    const {container} = render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    expect(await screen.findByTestId('jobagent-chat-page')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-cv-sidebar')).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText(/Start a conversation|History load issue/),
      ).toBeInTheDocument();
    });
  });

  it('removes stale chat while a persisted workspace reloads and remounts for the new identities', async () => {
    const first = deferred<ProfileListResponse>();
    const second = deferred<ProfileListResponse>();
    const profileA = appProfile('profile-a', true);
    const profileB = appProfile('profile-b', true);
    const conversationA = appConversation('conversation-a', profileA.id);
    const conversationB = appConversation('conversation-b', profileB.id);
    let profileRequest = 0;
    const fetchProfiles = vi.fn(() =>
      [first.promise, second.promise][profileRequest++],
    );
    const fetchProfileConversations = vi.fn((profileId: string) =>
      Promise.resolve({
        items: [profileId === profileA.id ? conversationA : conversationB],
        next_cursor: null,
      }),
    );
    const loadConversationHistory = vi.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
    });

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/profiles')) {
        return new Response(
          JSON.stringify({items: [], active_profile_id: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.includes('/api/profile') && !url.includes('/cv')) {
        return new Response(
          JSON.stringify({
            present: false,
            profile: null,
            preferences: null,
            active_attachment: null,
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      return new Response(JSON.stringify({items: [], next_cursor: null}), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      });
    });

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {fetchProfiles, fetchProfileConversations},
            chat: {loadConversationHistory},
          }}
        />
      </Theme>,
    );

    expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();
    first.resolve({items: [profileA], active_profile_id: profileA.id});
    await waitFor(() => expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument());
    await waitFor(() => expect(loadConversationHistory).toHaveBeenCalledTimes(1));

    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
    });
    await waitFor(() => expect(fetchProfiles).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();

    second.resolve({items: [profileB], active_profile_id: profileB.id});
    await waitFor(() => expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument());
    await waitFor(() => expect(loadConversationHistory).toHaveBeenCalledTimes(2));
    expect(loadConversationHistory.mock.calls.map(([id]) => id)).toEqual([
      conversationA.id,
      conversationB.id,
    ]);
  });

  it('switches to a validated tailoring workspace without remounting ChatPage', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const profileId = '11111111-1111-4111-8111-111111111111';
    const conversationId = '22222222-2222-4222-8222-222222222222';
    const sessionId = '33333333-3333-4333-8333-333333333333';
    const versionId = '44444444-4444-4444-8444-444444444444';
    const timestamp = '2026-07-26T00:00:00Z';
    const profile = {
      id: profileId,
      display_name: 'Synthetic CV',
      cv_filename: 'synthetic.pdf',
      attachment_state: 'active',
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: 'v1',
      source_hash: 'hash',
      state: 'ready' as const,
      setup_status: null,
      is_active: true,
      created_at: timestamp,
      updated_at: timestamp,
      last_opened_at: timestamp,
    };
    const loadConversationHistory = vi.fn().mockResolvedValue({
      items: [
        {
          id: '55555555-5555-4555-8555-555555555555',
          role: 'user',
          content: 'Tailor CV',
          structured_payload: null,
          created_at: timestamp,
          updated_at: timestamp,
          run: {
            id: '66666666-6666-4666-8666-666666666666',
            user_message_id: '55555555-5555-4555-8555-555555555555',
            state: 'completed',
            pending_approval: null,
            error_code: null,
            completed_at: timestamp,
            created_at: timestamp,
            updated_at: timestamp,
            activities: [],
            tool_executions: [
              {
                id: '77777777-7777-4777-8777-777777777777',
                tool_call_id: 'tool-call',
                tool_name: 'create_tailored_cv',
                status: 'completed',
                duration_ms: 1,
                error_code: null,
                created_at: timestamp,
                updated_at: timestamp,
                arguments_summary: null,
                result: {
                  ok: true,
                  code: null,
                  summary: 'ready',
                  data: {session_id: sessionId, version_id: versionId, status: 'ready', currentness: 'current'},
                },
              },
            ],
          },
        },
        {
          id: '88888888-8888-4888-8888-888888888888',
          role: 'assistant',
          content: 'Your tailored CV is ready.',
          structured_payload: null,
          created_at: timestamp,
          updated_at: timestamp,
          run: null,
        },
      ],
      next_cursor: null,
    });

    const fetchSession = vi.fn().mockResolvedValue({
      session: {
        id: sessionId,
        profile_id: profileId,
        job_label: null,
        instruction: 'Focus on verified evidence',
        template_version: 'latex-cv-v1',
        state: 'ready',
        currentness: 'current',
        latest_version_number: 1,
        error_code: null,
        created_at: timestamp,
        updated_at: timestamp,
      },
      versions: [
        {
          id: versionId,
          version_number: 1,
          parent_version_id: null,
          created_by: 'ai',
          page_count: 1,
          page_warning: null,
          created_at: timestamp,
        },
      ],
      selected_version: {
        id: versionId,
        version_number: 1,
        parent_version_id: null,
        created_by: 'ai',
        page_count: 1,
        page_warning: null,
        created_at: timestamp,
      },
      content: {
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
      },
      evidence: [],
      latest_run: null,
      source_available: true,
      pdf_available: true,
    });
    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [profile],
                active_profile_id: profileId,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [{id: conversationId, profile_id: profileId, title: 'Chat', created_at: timestamp, updated_at: timestamp, last_opened_at: timestamp, is_selected: true}],
                next_cursor: null,
              }),
            },
            chat: {loadConversationHistory},
            tailoring: {fetchSession},
          }}
        />
      </Theme>,
    );

    const openEditor = await screen.findByRole('button', {name: 'Mở CV đã chỉnh'});
    const chat = screen.getByTestId('jobagent-chat-page');
    await userEvent.click(openEditor);
    await waitFor(() => {
      expect(fetchSession).toHaveBeenCalledWith(sessionId, undefined, expect.any(AbortSignal));
    });
    expect(
      screen.getByRole('heading', {level: 1, name: 'CV đã chỉnh'}),
    ).toBeInTheDocument();
    const hiddenChatWorkspace = chat.closest('[hidden]');
    expect(hiddenChatWorkspace).not.toBeNull();
    expect(hiddenChatWorkspace).toHaveClass('jobagent-chat-workspace');
    expect(getComputedStyle(hiddenChatWorkspace as HTMLElement).display).toBe(
      'none',
    );
    expect(screen.getByTestId('jobagent-chat-page')).toBe(chat);
    expect(loadConversationHistory).toHaveBeenCalledTimes(1);
    await userEvent.click(
      screen.getByRole('button', {name: 'Quay lại chat'}),
    );
    await waitFor(() => {
      expect(
        screen.queryByRole('heading', {level: 1, name: 'CV đã chỉnh'}),
      ).not.toBeInTheDocument();
      expect(chat.closest('[hidden]')).toBeNull();
    });
    expect(screen.getByTestId('jobagent-chat-page')).toBe(chat);
  });
});

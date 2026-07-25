/**
 * Profile approval card + resume wiring tests (04B).
 * Streamed and restart-hydrated profile_commit cards, exact labels,
 * one accepted action, focus after request_changes, Save sidebar refresh.
 */
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {App} from '../app/App';
import {ChatPage, type ChatPageDeps} from '../features/chat/ChatPage';
import type {HistoryPage, SseEvent} from '../features/chat/types';
import type {StreamCallbacks} from '../lib/api/chat';
import {
  ApprovalCard,
  PROFILE_COMMIT_KIND,
  REQUEST_CHANGES_ACTION,
  REQUEST_CHANGES_LABEL,
  SAVE_PROFILE_ACTION,
  SAVE_PROFILE_LABEL,
  isProfileCommitApproval,
  parseProfileCommitProjection,
  summarizeApprovalCard,
} from '../features/profile/ApprovalCard';
import type {ProfileReadResponse} from '../features/profile/types';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const EVENT_C = '33333333-3333-4333-8333-333333333333';
const EVENT_D = '44444444-4444-4444-8444-444444444444';
const EVENT_E = '55555555-5555-4555-8555-555555555555';
const EVENT_F = '66666666-6666-4666-8666-666666666666';
const EVENT_G = '12121212-1212-4121-8121-121212121212';
const EVENT_H = '13131313-1313-4131-8131-131313131313';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const TS = '2026-07-13T12:00:00.000Z';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function emptyHistory(): HistoryPage {
  return {items: [], next_cursor: null};
}

function profileCommitCard(overrides?: Record<string, unknown>) {
  return {
    tool_name: 'commit_profile_draft',
    tool_call_id: 'tc-commit-1',
    draft_id: 'current',
    current_title: 'Backend Engineer',
    summary: 'API-focused engineer',
    skills: ['Python', 'TypeScript'],
    target_roles: ['Backend Engineer'],
    ...overrides,
  };
}

function interruptedHistory(card = profileCommitCard()): HistoryPage {
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Please commit my profile',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'interrupted',
          pending_approval: {
            kind: PROFILE_COMMIT_KIND,
            draft_id: 'current',
            allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
            card,
          },
          error_code: null,
          completed_at: null,
          created_at: TS,
          updated_at: TS,
          activities: [],
          tool_executions: [
            {
              id: TOOL_EXEC,
              tool_call_id: 'tc-commit-1',
              tool_name: 'commit_profile_draft',
              status: 'running',
              duration_ms: null,
              error_code: null,
              result: null,
              arguments_summary: {draft_id: 'current'},
              created_at: TS,
              updated_at: TS,
            },
          ],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'Review the proposed profile.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function sse(
  eventId: string,
  event: SseEvent['event'],
  payload: Record<string, unknown>,
  runId = RUN_ID,
): SseEvent {
  return {
    event_id: eventId,
    run_id: runId,
    timestamp: TS,
    event,
    payload,
  } as unknown as SseEvent;
}

function renderChat(deps: ChatPageDeps) {
  return render(
    <Theme theme={neutralTheme}>
      <ChatPage deps={deps} />
    </Theme>,
  );
}

function getComposerEditable(container: HTMLElement): HTMLElement {
  const editable =
    (container.querySelector(
      '[contenteditable="true"]',
    ) as HTMLElement | null) ??
    (container.querySelector(
      '[role="textbox"][contenteditable]',
    ) as HTMLElement | null) ??
    (container.querySelector('[role="textbox"]') as HTMLElement | null);
  if (!editable) {
    throw new Error('ChatComposer contentEditable not found');
  }
  return editable;
}

async function submitMessage(
  container: HTMLElement,
  text: string,
): Promise<void> {
  const user = userEvent.setup();
  const editable = getComposerEditable(container);
  await user.click(editable);
  await user.keyboard(text);
  const page = within(container);
  await waitFor(() => {
    const buttons = page.getAllByRole('button', {name: 'Send'});
    const enabled = buttons.find(
      (b) => !(b as HTMLButtonElement).disabled,
    );
    expect(enabled).toBeTruthy();
  });
  const send = page
    .getAllByRole('button', {name: 'Send'})
    .find((b) => !(b as HTMLButtonElement).disabled);
  if (!send) {
    throw new Error('Send button still disabled after typing');
  }
  await user.click(send);
}

describe('ApprovalCard pure helpers', () => {
  it('recognizes only profile_commit with both actions', () => {
    expect(
      isProfileCommitApproval(PROFILE_COMMIT_KIND, [
        SAVE_PROFILE_ACTION,
        REQUEST_CHANGES_ACTION,
      ]),
    ).toBe(true);
    expect(isProfileCommitApproval('confirm', ['approve', 'reject'])).toBe(
      false,
    );
    expect(isProfileCommitApproval(PROFILE_COMMIT_KIND, ['save_profile'])).toBe(
      false,
    );
  });

  it('summarizes compact fields without dumping raw CV', () => {
    const {title, lines} = summarizeApprovalCard({
      current_title: 'Engineer',
      summary: 'Short bio',
      skills: ['Go', 'Rust'],
      raw_cv_text: 'THIS MUST NOT APPEAR IN TITLE LOGIC PATHS',
    });
    expect(title).toBe('Engineer');
    expect(lines.some((l) => l.includes('Short bio'))).toBe(true);
    expect(lines.some((l) => l.includes('Go'))).toBe(true);
    // summarize only uses known keys — raw_cv_text is never listed as a line key
    expect(lines.join(' ')).not.toContain('THIS MUST NOT APPEAR');
  });

  it('parses durable pending_approval projection', () => {
    const parsed = parseProfileCommitProjection({
      kind: PROFILE_COMMIT_KIND,
      draft_id: 'current',
      allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
      card: profileCommitCard(),
    });
    expect(parsed).not.toBeNull();
    expect(parsed?.allowedActions).toEqual([
      SAVE_PROFILE_ACTION,
      REQUEST_CHANGES_ACTION,
    ]);
    expect(parsed?.card.current_title).toBe('Backend Engineer');
  });

  it('renders exact Save Profile and Request Changes labels', () => {
    const onAction = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <ApprovalCard
          card={profileCommitCard()}
          allowedActions={[SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION]}
          isDisabled={false}
          onAction={onAction}
        />
      </Theme>,
    );
    expect(
      screen.getByRole('button', {name: SAVE_PROFILE_LABEL}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
    ).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-approval-card')).toBeInTheDocument();
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument();
  });

  it('disables both buttons when isDisabled', async () => {
    const onAction = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <ApprovalCard
          card={profileCommitCard()}
          allowedActions={[SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION]}
          isDisabled
          onAction={onAction}
        />
      </Theme>,
    );
    const save = screen.getByRole('button', {name: SAVE_PROFILE_LABEL});
    const request = screen.getByRole('button', {name: REQUEST_CHANGES_LABEL});
    expect(save).toBeDisabled();
    expect(request).toBeDisabled();
    await userEvent.click(save);
    await userEvent.click(request);
    expect(onAction).not.toHaveBeenCalled();
  });
});

describe('Streamed profile_commit approval card', () => {
  it('renders one card with exact actions and locks composer/upload', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        cbs.onEvent(
          sse(EVENT_B, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-commit-1',
            tool_name: 'commit_profile_draft',
            status: 'running',
          }),
        );
        cbs.onEvent(
          sse(EVENT_C, 'approval_required', {
            state: 'interrupted',
            kind: PROFILE_COMMIT_KIND,
            allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
            card: profileCommitCard(),
          }),
        );
      },
    );
    const resumeRun = vi.fn();

    const {container} = renderChat({loadHistory, sendTurn, resumeRun});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'Commit please');

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-approval-card')).toBeInTheDocument();
    });
    expect(
      screen.getByRole('button', {name: SAVE_PROFILE_LABEL}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
    ).toBeInTheDocument();
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument();
    // No raw CV / storage path leakage
    expect(container.textContent).not.toMatch(/%PDF|storage_path/);
    expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
      'false',
    );
    expect(resumeRun).not.toHaveBeenCalled();
  });

  it('accepts only one action under rapid clicks and resumes once', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    let resolveResume: (() => void) | null = null;
    const resumeRun = vi.fn(
      async (
        runId: string,
        action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        expect(runId).toBe(RUN_ID);
        expect(action).toBe(SAVE_PROFILE_ACTION);
        // Hold before any SSE so the interrupt card remains for disable checks.
        await new Promise<void>((resolve) => {
          resolveResume = resolve;
        });
        cbs.onEvent(
          sse(EVENT_C, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_D, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-commit-1',
            tool_name: 'commit_profile_draft',
            status: 'completed',
            duration_ms: 20,
            summary: 'Profile saved',
          }),
        );
        cbs.onEvent(sse(EVENT_E, 'run_completed', {state: 'completed'}));
      },
    );
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        cbs.onEvent(
          sse(EVENT_B, 'approval_required', {
            state: 'interrupted',
            kind: PROFILE_COMMIT_KIND,
            allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
            card: profileCommitCard(),
          }),
        );
      },
    );

    const {container} = renderChat({loadHistory, sendTurn, resumeRun});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'Approve path');

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-approval-save')).toBeInTheDocument();
    });

    const save = screen.getByRole('button', {name: SAVE_PROFILE_LABEL});
    const request = screen.getByRole('button', {name: REQUEST_CHANGES_LABEL});
    // Rapid double-click Save + Request — only first accepted action fires.
    await userEvent.click(save);
    await userEvent.click(save);
    await userEvent.click(request);

    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    expect(resumeRun.mock.calls[0]![1]).toBe(SAVE_PROFILE_ACTION);

    // Buttons disabled after first accepted action (local lock; card still pending).
    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: SAVE_PROFILE_LABEL}),
      ).toBeDisabled();
      expect(
        screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
      ).toBeDisabled();
    });

    await act(async () => {
      resolveResume?.();
    });

    await waitFor(() => {
      expect(screen.queryByTestId('jobagent-approval-card')).not.toBeInTheDocument();
    });
    void container;
  });

  it('request_changes completion unlocks and focuses composer', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const resumeRun = vi.fn(
      async (
        _runId: string,
        action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        expect(action).toBe(REQUEST_CHANGES_ACTION);
        cbs.onEvent(
          sse(EVENT_C, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_D, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-commit-1',
            tool_name: 'commit_profile_draft',
            status: 'completed',
            duration_ms: 5,
            summary: 'Changes requested',
          }),
        );
        cbs.onEvent(sse(EVENT_E, 'run_completed', {state: 'completed'}));
      },
    );
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        cbs.onEvent(
          sse(EVENT_B, 'approval_required', {
            state: 'interrupted',
            kind: PROFILE_COMMIT_KIND,
            allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
            card: profileCommitCard(),
          }),
        );
      },
    );

    const {container} = renderChat({loadHistory, sendTurn, resumeRun});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'Need edits');

    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
      ).toBeInTheDocument();
    });
    await userEvent.click(
      screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
    );

    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
        'true',
      );
    });

    // Documented composer surface receives focus after request_changes.
    await waitFor(() => {
      const editable = getComposerEditable(container);
      expect(
        document.activeElement === editable ||
          editable.contains(document.activeElement),
      ).toBe(true);
    });
  });

  it('renders truthful failure for commit/sync errors without false success', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const resumeRun = vi.fn(
      async (
        _runId: string,
        _action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_C, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_D, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-commit-1',
            tool_name: 'commit_profile_draft',
            status: 'failed',
            duration_ms: 12,
            summary: 'SQLite committed; Neo4j sync failed',
            error_code: 'NEO4J_SYNC_FAILED',
            activity: {
              activity_id: TOOL_EXEC,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'tool',
              label: 'Save CV profile',
              technical_name: 'commit_profile_draft',
              state: 'failed',
              started_at: TS,
              updated_at: TS,
              completed_at: TS,
              duration_ms: 12,
              error_code: 'NEO4J_SYNC_FAILED',
            },
          }),
        );
        cbs.onEvent(
          sse(EVENT_E, 'run_failed', {
            state: 'failed',
            error_code: 'NEO4J_SYNC_FAILED',
            summary: 'Profile saved in SQLite but graph sync failed',
          }),
        );
      },
    );
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        cbs.onEvent(
          sse(EVENT_B, 'approval_required', {
            state: 'interrupted',
            kind: PROFILE_COMMIT_KIND,
            allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
            card: profileCommitCard(),
          }),
        );
      },
    );

    const {container} = renderChat({loadHistory, sendTurn, resumeRun});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'Save with sync fail');
    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: SAVE_PROFILE_LABEL}),
      ).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', {name: SAVE_PROFILE_LABEL}));

    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      // Visible truthful failure: stream notice and/or exact tool status.
      const body = document.body.textContent ?? '';
      expect(body).toMatch(/NEO4J_SYNC_FAILED|graph sync failed|Neo4j sync failed/i);
      expect(body).toMatch(/\bfailed\b/);
      expect(body).not.toMatch(/saved successfully/i);
    });
    expect(
      screen.getByText(
        'commit_profile_draft · failed · 12ms · NEO4J_SYNC_FAILED',
      ),
    ).toBeInTheDocument();
    void container;
  });
});

describe('Restart-hydrated profile_commit card', () => {
  it('reconstructs pending card from durable run metadata', async () => {
    const loadHistory = vi.fn().mockResolvedValue(interruptedHistory());
    const resumeRun = vi.fn();
    const {container} = renderChat({
      loadHistory,
      sendTurn: vi.fn(),
      resumeRun,
    });

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-approval-card')).toBeInTheDocument();
    });
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: SAVE_PROFILE_LABEL}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
    ).toBeInTheDocument();
    // Composer locked from hydrated interrupt
    expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
      'false',
    );
    expect(resumeRun).not.toHaveBeenCalled();
  });
});

describe('Save Profile refreshes sidebar', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
        takeRecords() {
          return [];
        }
      },
    );
  });

  it('reloads pending setup before enabling Request Changes correction', async () => {
    const profileId = 'abababab-abab-4bab-8bab-abababababab';
    const conversationId = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd';
    const awaitingExtraction = {
      id: profileId,
      display_name: 'pending.pdf',
      cv_filename: 'pending.pdf',
      attachment_state: 'staged' as const,
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: null,
      source_hash: null,
      state: 'pending' as const,
      setup_status: 'awaiting_extraction' as const,
      is_active: true,
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
    };
    const awaitingApproval = {
      ...awaitingExtraction,
      setup_status: 'awaiting_approval' as const,
    };
    const conversation = {
      id: conversationId,
      profile_id: profileId,
      title: 'Chat mới',
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
      is_selected: true,
    };
    const fetchProfiles = vi
      .fn()
      .mockResolvedValueOnce({
        items: [],
        active_profile_id: null,
      })
      .mockResolvedValue({
        items: [awaitingApproval],
        active_profile_id: profileId,
      });
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [conversation],
      next_cursor: null,
    });
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const uploadCv = vi.fn().mockResolvedValue({
      attachment: {
        id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        original_name: 'pending.pdf',
        mime_type: 'application/pdf' as const,
        size_bytes: 100,
        page_count: 1,
        state: 'staged' as const,
        failure_code: null,
      },
      outcome: 'new_pending' as const,
      profile: null,
      draft: null,
      bootstrap: {
        profile: awaitingExtraction,
        conversation,
        start_extraction: true,
      },
    });
    let emitApproval: (() => void) | null = null;
    const sendConversationTurn = vi.fn(
      async (
        _conversationId: string,
        _body: {message: string; attachment_ids?: string[]},
        callbacks: StreamCallbacks,
      ) => {
        await new Promise<void>((resolve) => {
          emitApproval = () => {
            callbacks.onEvent(
              sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
            );
            callbacks.onEvent(
              sse(EVENT_B, 'approval_required', {
                state: 'interrupted',
                kind: PROFILE_COMMIT_KIND,
                allowed_actions: [SAVE_PROFILE_ACTION, REQUEST_CHANGES_ACTION],
                card: profileCommitCard(),
              }),
            );
            resolve();
          };
        });
      },
    );
    const resumeRun = vi.fn(
      async (
        _runId: string,
        action: string,
        callbacks: StreamCallbacks,
      ) => {
        expect(action).toBe(REQUEST_CHANGES_ACTION);
        callbacks.onEvent(
          sse(EVENT_F, 'run_started', {state: 'running', resumed: true}),
        );
        callbacks.onEvent(
          sse(EVENT_G, 'run_completed', {state: 'completed'}),
        );
      },
    );

    const {container} = render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {
              loadHistory,
              loadConversationHistory: loadHistory,
              sendTurn: vi.fn(),
              sendConversationTurn,
              resumeRun,
              uploadCv,
            },
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue({
                present: false,
                profile: null,
                preferences: null,
                active_attachment: null,
                draft_present: true,
                pending_attachment: null,
              }),
              uploadCv,
              getActiveCvUrl: () => 'http://localhost/api/profile/cv',
            },
            workspace: {fetchProfiles, fetchProfileConversations},
          }}
        />
      </Theme>,
    );

    await userEvent.upload(
      screen.getByTestId('jobagent-cv-upload'),
      new File(['%PDF-1.4'], 'pending.pdf', {type: 'application/pdf'}),
    );
    await waitFor(() => expect(uploadCv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(sendConversationTurn).toHaveBeenCalledTimes(1));
    await act(async () => {
      emitApproval?.();
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-approval-card')).toBeInTheDocument();
    });
    expect(getComposerEditable(container)).toHaveAttribute(
      'contenteditable',
      'false',
    );

    await userEvent.click(
      screen.getByRole('button', {name: REQUEST_CHANGES_LABEL}),
    );

    await waitFor(() => expect(resumeRun).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fetchProfiles.mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => {
      expect(getComposerEditable(container)).toHaveAttribute(
        'contenteditable',
        'true',
      );
    });
  });

  it('bumps profile reload after save_profile completes', async () => {
    const profileId = 'abababab-abab-4bab-8bab-abababababab';
    const conversationId = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd';
    const pendingProfile = {
      id: profileId,
      display_name: 'pending.pdf',
      cv_filename: 'pending.pdf',
      attachment_state: 'staged' as const,
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: null,
      source_hash: null,
      state: 'pending' as const,
      setup_status: 'awaiting_approval' as const,
      is_active: true,
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
    };
    const readyProfile = {
      ...pendingProfile,
      attachment_state: 'active' as const,
      extraction_version: 'cv-document-v1',
      source_hash: 'approved-source-hash',
      state: 'ready' as const,
      setup_status: null,
    };
    const conversation = {
      id: conversationId,
      profile_id: profileId,
      title: 'Chat mới',
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
      is_selected: true,
    };
    const fetchProfiles = vi
      .fn()
      .mockResolvedValueOnce({items: [pendingProfile], active_profile_id: profileId})
      .mockResolvedValue({items: [readyProfile], active_profile_id: profileId});
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [conversation],
      next_cursor: null,
    });
    let profileCalls = 0;
    const loadProfile = vi.fn(async (): Promise<ProfileReadResponse> => {
      profileCalls += 1;
      if (profileCalls === 1) {
        return {
          present: false,
          profile: null,
          preferences: null,
          active_attachment: null,
          draft_present: false,
          pending_attachment: null,
        };
      }
      return {
        present: true,
        profile: {
          summary: 'Approved',
          current_title: 'Senior Backend Engineer',
        },
        preferences: {
          target_roles: ['Backend'],
          preferred_locations: [],
          acceptable_work_modes: [],
          target_seniority: [],
        },
        active_attachment: {
          id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          original_name: 'approved-cv.pdf',
          mime_type: 'application/pdf',
          size_bytes: 100,
          page_count: 1,
          state: 'active',
          failure_code: null,
        },
        draft_present: false,
        pending_attachment: null,
      };
    });

    const loadHistory = vi.fn().mockResolvedValue(interruptedHistory());
    const resumeRun = vi.fn(
      async (
        _runId: string,
        action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        expect(action).toBe(SAVE_PROFILE_ACTION);
        cbs.onEvent(
          sse(EVENT_F, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_G, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-commit-1',
            tool_name: 'commit_profile_draft',
            status: 'completed',
            duration_ms: 30,
            summary: 'Profile committed',
          }),
        );
        cbs.onEvent(sse(EVENT_H, 'run_completed', {state: 'completed'}));
      },
    );

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {
              loadHistory,
              loadConversationHistory: loadHistory,
              sendTurn: vi.fn(),
              resumeRun,
              uploadCv: vi.fn(),
            },
            sidebar: {
              loadProfile,
              uploadCv: vi.fn(),
              getActiveCvUrl: () => 'http://localhost/api/profile/cv',
            },
            workspace: {fetchProfiles, fetchProfileConversations},
          }}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-approval-card')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', {name: SAVE_PROFILE_LABEL}));

    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(loadProfile.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(fetchProfiles.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
        'Senior Backend Engineer',
      );
    });
  });

  it('Save Profile fans out profile, activation, and saved-JD invalidation once', async () => {
    const {cvHistoryPage, mockObservabilityApi} = await import(
      './support/observability'
    );
    const profileId = 'abababab-abab-4bab-8bab-abababababab';
    const conversationId = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd';
    const baselineProfile = {
      id: profileId,
      display_name: 'Existing profile',
      cv_filename: 'pending.pdf',
      attachment_state: 'active' as const,
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: 'cv-document-v0',
      source_hash: 'previous-source-hash',
      state: 'ready' as const,
      setup_status: null,
      is_active: true,
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
    };
    const readyProfile = {
      ...baselineProfile,
      extraction_version: 'cv-document-v1',
      source_hash: 'approved-source-hash',
    };
    const conversation = {
      id: conversationId,
      profile_id: profileId,
      title: 'Chat má»›i',
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
      is_selected: true,
    };
    const fetchProfiles = vi
      .fn()
      .mockResolvedValueOnce({items: [baselineProfile], active_profile_id: profileId})
      .mockResolvedValue({items: [readyProfile], active_profile_id: profileId});
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [conversation],
      next_cursor: null,
    });
    let profileCalls = 0;
    const loadProfile = vi.fn(async (): Promise<ProfileReadResponse> => {
      profileCalls += 1;
      if (profileCalls === 1) {
        return {
          present: false,
          profile: null,
          preferences: null,
          active_attachment: null,
          draft_present: true,
          pending_attachment: null,
        };
      }
      return {
        present: true,
        profile: {
          summary: 'Approved',
          current_title: 'Senior Backend Engineer',
        },
        preferences: {
          target_roles: ['Backend'],
          preferred_locations: [],
          acceptable_work_modes: [],
          target_seniority: [],
        },
        active_attachment: {
          id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          original_name: 'approved-cv.pdf',
          mime_type: 'application/pdf',
          size_bytes: 100,
          page_count: 1,
          state: 'active',
          failure_code: null,
        },
        draft_present: false,
        pending_attachment: null,
      };
    });

    const firstCv = cvHistoryPage();
    const secondCv = cvHistoryPage();
    secondCv.items[0] = {
      ...secondCv.items[0]!,
      original_name: 'post-save.pdf',
      state: 'active',
    };
    const fetchCvHistory = vi
      .fn()
      .mockResolvedValueOnce(firstCv)
      .mockResolvedValueOnce(secondCv);
    const observability = mockObservabilityApi({fetchCvHistory});

    const jobId = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
    const currentList = {
      items: [
        {
          id: jobId,
          title: 'Backend Engineer',
          company: 'Acme',
          processing_status: 'processed',
          jd_quality: 'full',
          source_type: 'text',
          source_url: null,
          created_at: TS,
          updated_at: TS,
          evaluation_state: 'current',
          latest_score: 0.9,
        },
      ],
      next_cursor: null,
    };
    const staleList = {
      items: [
        {
          ...currentList.items[0]!,
          evaluation_state: 'stale',
        },
      ],
      next_cursor: null,
    };
    let jobsListCalls = 0;
    const evaluateCalls: string[] = [];
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? 'GET').toUpperCase();
        if (url.includes('/api/jobs') && method === 'POST') {
          evaluateCalls.push(url);
          return new Response(JSON.stringify({error: 'unexpected'}), {
            status: 500,
            headers: {'Content-Type': 'application/json'},
          });
        }
        if (url.includes(`/api/jobs/${jobId}`) && method === 'GET') {
          const compact = jobsListCalls > 1 ? staleList.items[0]! : currentList.items[0]!;
          return new Response(
            JSON.stringify({
              compact,
              extraction: null,
              raw_content: null,
              latest_evaluation: null,
            }),
            {status: 200, headers: {'Content-Type': 'application/json'}},
          );
        }
        if (url.includes('/api/jobs') && method === 'GET') {
          jobsListCalls += 1;
          const body = jobsListCalls === 1 ? currentList : staleList;
          return new Response(JSON.stringify(body), {
            status: 200,
            headers: {'Content-Type': 'application/json'},
          });
        }
        return new Response(JSON.stringify({}), {
          status: 404,
          headers: {'Content-Type': 'application/json'},
        });
      });

    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation of Vite env
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    try {
      const loadHistory = vi.fn().mockResolvedValue(interruptedHistory());
      const resumeRun = vi.fn(
        async (
          _runId: string,
          action: string,
          cbs: StreamCallbacks,
          _signal?: AbortSignal,
        ) => {
          expect(action).toBe(SAVE_PROFILE_ACTION);
          cbs.onEvent(
            sse(EVENT_F, 'run_started', {state: 'running', resumed: true}),
          );
          cbs.onEvent(
            sse(EVENT_G, 'tool_status', {
              tool_execution_id: TOOL_EXEC,
              tool_call_id: 'tc-commit-1',
              tool_name: 'commit_profile_draft',
              status: 'completed',
              duration_ms: 30,
              summary: 'Profile committed',
            }),
          );
          cbs.onEvent(sse(EVENT_H, 'run_completed', {state: 'completed'}));
        },
      );

      render(
        <Theme theme={neutralTheme}>
          <App
            deps={{
              chat: {
                loadHistory,
                loadConversationHistory: loadHistory,
                sendTurn: vi.fn(),
                resumeRun,
                uploadCv: vi.fn(),
              },
              sidebar: {
                loadProfile,
                uploadCv: vi.fn(),
                getActiveCvUrl: () => 'http://localhost/api/profile/cv',
                observability,
              },
              workspace: {fetchProfiles, fetchProfileConversations},
            }}
          />
        </Theme>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('jobagent-approval-card')).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(fetchProfiles).toHaveBeenCalled();
        expect(fetchProfileConversations).toHaveBeenCalledWith(profileId, {limit: 50});
        expect(screen.getByTestId('jobagent-profile-list-panel')).toHaveTextContent(
          'Existing profile',
        );
      });

      // Seed CV Manager cache, then open saved-JD (activation while JD tab open).
      await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
      expect(await screen.findByText('archived.pdf')).toBeInTheDocument();
      expect(fetchCvHistory).toHaveBeenCalledTimes(1);

      await userEvent.click(screen.getByRole('tab', {name: 'JD đã lưu'}));
      await waitFor(() => {
        expect(jobsListCalls).toBeGreaterThanOrEqual(1);
      });
      expect(
        await screen.findByTestId(`jobagent-saved-job-select-${jobId}`),
      ).toBeInTheDocument();
      await userEvent.click(
        screen.getByTestId(`jobagent-saved-job-select-${jobId}`),
      );

      const profileBefore = loadProfile.mock.calls.length;
      const jobsBefore = jobsListCalls;
      const cvBefore = fetchCvHistory.mock.calls.length;

      await userEvent.click(
        screen.getByRole('button', {name: SAVE_PROFILE_LABEL}),
      );

      await waitFor(() => {
        expect(resumeRun).toHaveBeenCalledTimes(1);
      });
      // Profile refresh signal.
      await waitFor(() => {
        expect(loadProfile.mock.calls.length).toBe(profileBefore + 1);
      });
      // Saved-JD invalidation while open → list/detail GET; no evaluate POST.
      await waitFor(() => {
        expect(jobsListCalls).toBeGreaterThan(jobsBefore);
      });
      expect(evaluateCalls).toHaveLength(0);
      await waitFor(() => {
        expect(
          screen.getByTestId(`jobagent-saved-job-stale-badge-${jobId}`),
        ).toBeInTheDocument();
      });
      // Activation marked CV non-current without a fetch while the tab was closed.
      expect(fetchCvHistory.mock.calls.length).toBe(cvBefore);

      // Returning to CV Manager performs the deferred activation reload once.
      await userEvent.click(screen.getByTestId('jobagent-obs-tab-cv-history'));
      await waitFor(() => {
        expect(fetchCvHistory.mock.calls.length).toBe(cvBefore + 1);
      });
      expect(await screen.findByText('post-save.pdf')).toBeInTheDocument();

      // Single fan-out: each of the three signals advanced once.
      expect(loadProfile.mock.calls.length - profileBefore).toBe(1);
      expect(fetchCvHistory.mock.calls.length - cvBefore).toBe(1);
      expect(jobsListCalls - jobsBefore).toBeGreaterThanOrEqual(1);
    } finally {
      fetchMock.mockRestore();
      // @ts-expect-error restore Vite env
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

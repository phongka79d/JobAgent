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
    // Exact tool status vocabulary remains failed (not complete/error aliases).
    expect(screen.getByText('failed')).toBeInTheDocument();
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

  it('bumps profile reload after save_profile completes', async () => {
    let profileCalls = 0;
    const loadProfile = vi.fn(async (): Promise<ProfileReadResponse> => {
      profileCalls += 1;
      if (profileCalls === 1) {
        return {
          present: false,
          profile: null,
          preferences: null,
          active_attachment: null,
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
              sendTurn: vi.fn(),
              resumeRun,
              uploadCv: vi.fn(),
            },
            sidebar: {
              loadProfile,
              uploadCv: vi.fn(),
              getActiveCvUrl: () => 'http://localhost/api/profile/cv',
            },
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
      expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
        'Senior Backend Engineer',
      );
    });
  });
});

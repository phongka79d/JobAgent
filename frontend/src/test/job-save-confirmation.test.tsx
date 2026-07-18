/**
 * Pasted-JD save confirmation parser/card + resume wiring (Plan 12 Batch04 04A).
 * Strict projection, exact Vietnamese copy, shared resume lock, Review JD,
 * cancel without SavedJobCard/invalidation, committed-only invalidation.
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
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ChatPage, type ChatPageDeps} from '../features/chat/ChatPage';
import {
  CANCEL_SAVE_JOB_ACTION,
  CANCEL_SAVE_JOB_LABEL,
  CURRENT_MESSAGE_SOURCE,
  historyPageHasCommittedSaveJob,
  isJobSaveConfirmationApproval,
  JD_CONFIRMATION_HEADING,
  JD_CONFIRMATION_SENTENCE,
  JOB_SAVE_CONFIRMATION_KIND,
  jobSaveConfirmationForRow,
  parseJobSaveConfirmationProjection,
  REVIEW_JD_LABEL,
  SAVE_JOB_ACTION,
  SAVE_JOB_LABEL,
  shouldLabelReviewJd,
} from '../features/chat/jobSaveConfirmation';
import {JobSaveConfirmationCard} from '../features/chat/components/JobSaveConfirmationCard';
import type {ClientMessage, ClientRun} from '../features/chat/reducer';
import type {HistoryPage, JsonObject, SseEvent} from '../features/chat/types';
import type {StreamCallbacks} from '../lib/api/chat';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const RUN_OTHER = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const EVENT_C = '33333333-3333-4333-8333-333333333333';
const EVENT_D = '44444444-4444-4444-8444-444444444444';
const EVENT_E = '55555555-5555-4555-8555-555555555555';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const JOB_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const TS = '2026-07-18T12:00:00.000Z';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function emptyHistory(): HistoryPage {
  return {items: [], next_cursor: null};
}

function validCard(overrides?: Record<string, unknown>): JsonObject {
  return {
    tool_name: 'save_job',
    tool_call_id: 'tc-save-jd-1',
    source: CURRENT_MESSAGE_SOURCE,
    text_length: 420,
    preview: {
      title: 'Backend Engineer',
      company: 'Acme',
      skills: ['Python', 'SQL'],
    },
    ...overrides,
  };
}

function validPending(overrides?: Record<string, unknown>): JsonObject {
  return {
    kind: JOB_SAVE_CONFIRMATION_KIND,
    allowed_actions: [SAVE_JOB_ACTION, CANCEL_SAVE_JOB_ACTION],
    card: validCard(),
    ...overrides,
  };
}

function compactSaveData(overrides?: JsonObject): JsonObject {
  return {
    job_id: JOB_ID,
    title: 'Backend Engineer',
    company: 'Acme',
    source_url: null,
    processing_status: 'processed',
    jd_quality: 'full',
    outcome: 'created',
    sqlite_committed: true,
    sync_ok: true,
    failure_code: null,
    rebuild_instruction: null,
    paste_instruction: null,
    ...overrides,
  };
}

function interruptedHistory(
  pending: JsonObject = validPending(),
): HistoryPage {
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Job Description\nResponsibilities\nRequirements\nSkills\nMore text here to pass length',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'interrupted',
          pending_approval: pending,
          error_code: null,
          completed_at: null,
          created_at: TS,
          updated_at: TS,
          tool_executions: [
            {
              id: TOOL_EXEC,
              tool_call_id: 'tc-save-jd-1',
              tool_name: 'save_job',
              status: 'running',
              duration_ms: null,
              error_code: null,
              result: null,
              arguments_summary: {source: 'current_message'},
              created_at: TS,
              updated_at: TS,
            },
          ],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'JD này chưa được lưu.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function terminalCommittedHistory(): HistoryPage {
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'pasted jd body',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'completed',
          pending_approval: null,
          error_code: null,
          completed_at: TS,
          created_at: TS,
          updated_at: TS,
          tool_executions: [
            {
              id: TOOL_EXEC,
              tool_call_id: 'tc-save-jd-1',
              tool_name: 'save_job',
              status: 'completed',
              duration_ms: 40,
              error_code: null,
              result: {
                ok: true,
                code: null,
                summary: 'Saved job description',
                data: compactSaveData(),
              },
              arguments_summary: {source: 'current_message'},
              created_at: TS,
              updated_at: TS,
            },
          ],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'Đã lưu JD.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function terminalCancelledHistory(): HistoryPage {
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'pasted jd body',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'completed',
          pending_approval: null,
          error_code: null,
          completed_at: TS,
          created_at: TS,
          updated_at: TS,
          tool_executions: [
            {
              id: TOOL_EXEC,
              tool_call_id: 'tc-save-jd-1',
              tool_name: 'save_job',
              status: 'completed',
              duration_ms: 5,
              error_code: null,
              result: {
                ok: true,
                code: null,
                summary: 'JD chưa được lưu',
                data: {committed: false, outcome: 'cancelled'},
              },
              arguments_summary: {source: 'current_message'},
              created_at: TS,
              updated_at: TS,
            },
          ],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'JD chưa được lưu.',
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

function renderChat(deps: ChatPageDeps, props?: {onSavedJobsInvalidated?: () => void}) {
  return render(
    <Theme theme={neutralTheme}>
      <ChatPage deps={deps} onSavedJobsInvalidated={props?.onSavedJobsInvalidated} />
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

describe('parseJobSaveConfirmationProjection', () => {
  it('accepts the exact source-defined projection', () => {
    const parsed = parseJobSaveConfirmationProjection(validPending());
    expect(parsed).not.toBeNull();
    expect(parsed?.kind).toBe(JOB_SAVE_CONFIRMATION_KIND);
    expect(parsed?.allowedActions).toEqual([
      SAVE_JOB_ACTION,
      CANCEL_SAVE_JOB_ACTION,
    ]);
    expect(parsed?.card.toolName).toBe('save_job');
    expect(parsed?.card.source).toBe(CURRENT_MESSAGE_SOURCE);
    expect(parsed?.card.textLength).toBe(420);
    expect(parsed?.card.preview.title).toBe('Backend Engineer');
    expect(parsed?.card.preview.skills).toEqual(['Python', 'SQL']);
  });

  it('accepts null optional preview fields and empty skills', () => {
    const parsed = parseJobSaveConfirmationProjection(
      validPending({
        card: validCard({
          preview: {title: null, company: null, skills: []},
        }),
      }),
    );
    expect(parsed).not.toBeNull();
    expect(parsed?.card.preview.title).toBeNull();
    expect(parsed?.card.preview.company).toBeNull();
    expect(parsed?.card.preview.skills).toEqual([]);
  });

  it('rejects wrong kind, missing actions, duplicates, and extras', () => {
    expect(
      parseJobSaveConfirmationProjection(
        validPending({kind: 'profile_commit'}),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({allowed_actions: [SAVE_JOB_ACTION]}),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          allowed_actions: [SAVE_JOB_ACTION, SAVE_JOB_ACTION],
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          allowed_actions: [
            SAVE_JOB_ACTION,
            CANCEL_SAVE_JOB_ACTION,
            'extra',
          ],
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({draft_id: 'current'}),
      ),
    ).toBeNull();
  });

  it('rejects forbidden keys and over-limit fields', () => {
    expect(
      parseJobSaveConfirmationProjection(
        validPending({text: 'raw jd body'}),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({message_id: MSG_USER}),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({
            preview: {
              title: 'T',
              company: null,
              skills: [],
              url: 'https://evil.example',
            },
          }),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({text_length: 0}),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({text_length: 1_000_001}),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({
            preview: {
              title: 'x'.repeat(161),
              company: null,
              skills: [],
            },
          }),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({
            preview: {
              title: null,
              company: null,
              skills: ['a', 'b', 'c', 'd', 'e', 'f'],
            },
          }),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({source: 'text'}),
        }),
      ),
    ).toBeNull();
    expect(
      parseJobSaveConfirmationProjection(
        validPending({
          card: validCard({tool_name: 'match_jobs'}),
        }),
      ),
    ).toBeNull();
  });

  it('isJobSaveConfirmationApproval requires exact pair', () => {
    expect(
      isJobSaveConfirmationApproval(JOB_SAVE_CONFIRMATION_KIND, [
        SAVE_JOB_ACTION,
        CANCEL_SAVE_JOB_ACTION,
      ]),
    ).toBe(true);
    expect(
      isJobSaveConfirmationApproval(JOB_SAVE_CONFIRMATION_KIND, [
        CANCEL_SAVE_JOB_ACTION,
        SAVE_JOB_ACTION,
      ]),
    ).toBe(true);
    expect(
      isJobSaveConfirmationApproval('profile_commit', [
        SAVE_JOB_ACTION,
        CANCEL_SAVE_JOB_ACTION,
      ]),
    ).toBe(false);
  });
});

describe('JobSaveConfirmationCard presentation', () => {
  it('renders exact Vietnamese heading, sentence, and action order', () => {
    const onAction = vi.fn();
    const parsed = parseJobSaveConfirmationProjection(validPending())!;
    render(
      <Theme theme={neutralTheme}>
        <JobSaveConfirmationCard
          card={parsed.card}
          allowedActions={parsed.allowedActions}
          isDisabled={false}
          onAction={onAction}
          runId={RUN_ID}
        />
      </Theme>,
    );
    expect(screen.getByText(JD_CONFIRMATION_HEADING)).toBeInTheDocument();
    expect(screen.getByText(JD_CONFIRMATION_SENTENCE)).toBeInTheDocument();
    expect(screen.getByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('SQL')).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    const labels = buttons.map((b) => b.textContent ?? '');
    const saveIdx = labels.findIndex((l) => l.includes(SAVE_JOB_LABEL));
    const cancelIdx = labels.findIndex((l) =>
      l.includes(CANCEL_SAVE_JOB_LABEL),
    );
    expect(saveIdx).toBeGreaterThanOrEqual(0);
    expect(cancelIdx).toBeGreaterThan(saveIdx);
  });

  it('omits absent optional preview rows without inventing facts', () => {
    const parsed = parseJobSaveConfirmationProjection(
      validPending({
        card: validCard({
          preview: {title: null, company: null, skills: []},
        }),
      }),
    )!;
    render(
      <Theme theme={neutralTheme}>
        <JobSaveConfirmationCard
          card={parsed.card}
          allowedActions={parsed.allowedActions}
          isDisabled={false}
          onAction={vi.fn()}
        />
      </Theme>,
    );
    expect(screen.getByText(JD_CONFIRMATION_HEADING)).toBeInTheDocument();
    expect(screen.queryByText('Title')).not.toBeInTheDocument();
    expect(screen.queryByText('Company')).not.toBeInTheDocument();
    expect(screen.getByText('420')).toBeInTheDocument();
  });

  it('disables both actions when locked', () => {
    const parsed = parseJobSaveConfirmationProjection(validPending())!;
    render(
      <Theme theme={neutralTheme}>
        <JobSaveConfirmationCard
          card={parsed.card}
          allowedActions={parsed.allowedActions}
          isDisabled
          onAction={vi.fn()}
        />
      </Theme>,
    );
    expect(screen.getByRole('button', {name: SAVE_JOB_LABEL})).toBeDisabled();
    expect(
      screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
    ).toBeDisabled();
  });
});

describe('jobSaveConfirmationForRow association', () => {
  function runWithPending(pending: JsonObject): ClientRun {
    return {
      id: RUN_ID,
      userMessageId: MSG_USER,
      state: 'interrupted',
      pendingApproval: pending,
      errorCode: null,
      completedAt: null,
      tools: [
        {
          toolExecutionId: TOOL_EXEC,
          toolCallId: 'tc-save-jd-1',
          toolName: 'save_job',
          status: 'running',
          durationMs: null,
          summary: null,
          errorCode: null,
          source: 'history',
          resultData: null,
        },
      ],
    };
  }

  it('hosts the card on the assistant row from preceding user run', () => {
    const messages: ClientMessage[] = [
      {
        id: MSG_USER,
        clientKey: MSG_USER,
        role: 'user',
        content: 'jd',
        createdAt: TS,
        run: runWithPending(validPending()),
        isStreaming: false,
      },
      {
        id: MSG_ASST,
        clientKey: MSG_ASST,
        role: 'assistant',
        content: 'unsaved',
        createdAt: TS,
        run: null,
        isStreaming: false,
      },
    ];
    expect(jobSaveConfirmationForRow(messages, 0)).toBeNull();
    const host = jobSaveConfirmationForRow(messages, 1);
    expect(host?.run.id).toBe(RUN_ID);
    expect(host?.projection.card.toolCallId).toBe('tc-save-jd-1');
  });

  it('does not cross into a neighboring assistant/run', () => {
    const messages: ClientMessage[] = [
      {
        id: MSG_USER,
        clientKey: MSG_USER,
        role: 'user',
        content: 'jd',
        createdAt: TS,
        run: runWithPending(validPending()),
        isStreaming: false,
      },
      {
        id: MSG_ASST,
        clientKey: MSG_ASST,
        role: 'assistant',
        content: 'first',
        createdAt: TS,
        run: null,
        isStreaming: false,
      },
      {
        id: 'asst-2',
        clientKey: 'asst-2',
        role: 'assistant',
        content: 'other',
        createdAt: TS,
        run: {
          id: RUN_OTHER,
          userMessageId: 'other-user',
          state: 'completed',
          pendingApproval: null,
          errorCode: null,
          completedAt: TS,
          tools: [],
        },
        isStreaming: false,
      },
    ];
    expect(jobSaveConfirmationForRow(messages, 2)).toBeNull();
  });

  it('rejects malformed pending as no card host', () => {
    const messages: ClientMessage[] = [
      {
        id: MSG_USER,
        clientKey: MSG_USER,
        role: 'user',
        content: 'jd',
        createdAt: TS,
        run: runWithPending(validPending({text: 'leak'})),
        isStreaming: false,
      },
      {
        id: MSG_ASST,
        clientKey: MSG_ASST,
        role: 'assistant',
        content: 'x',
        createdAt: TS,
        run: null,
        isStreaming: false,
      },
    ];
    expect(jobSaveConfirmationForRow(messages, 1)).toBeNull();
  });
});

describe('Review JD presentation helper', () => {
  it('labels only running/pending save_job while review active', () => {
    expect(shouldLabelReviewJd('save_job', 'running', true)).toBe(true);
    expect(shouldLabelReviewJd('save_job', 'pending', true)).toBe(true);
    expect(shouldLabelReviewJd('save_job', 'completed', true)).toBe(false);
    expect(shouldLabelReviewJd('save_job', 'running', false)).toBe(false);
    expect(shouldLabelReviewJd('match_jobs', 'running', true)).toBe(false);
    expect(REVIEW_JD_LABEL).toBe('Review JD');
  });
});

describe('historyPageHasCommittedSaveJob', () => {
  it('requires validated sqlite_committed true for the run', () => {
    expect(
      historyPageHasCommittedSaveJob(terminalCommittedHistory(), RUN_ID),
    ).toBe(true);
    expect(
      historyPageHasCommittedSaveJob(terminalCancelledHistory(), RUN_ID),
    ).toBe(false);
    expect(
      historyPageHasCommittedSaveJob(terminalCommittedHistory(), RUN_OTHER),
    ).toBe(false);
  });
});

describe('Live and restart JD confirmation host', () => {
  it('renders one card from live approval_required SSE', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const resumeRun = vi.fn();
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
            tool_call_id: 'tc-save-jd-1',
            tool_name: 'save_job',
            status: 'running',
            duration_ms: null,
            summary: null,
          }),
        );
        cbs.onEvent(
          sse(EVENT_C, 'approval_required', {
            state: 'interrupted',
            kind: JOB_SAVE_CONFIRMATION_KIND,
            allowed_actions: [SAVE_JOB_ACTION, CANCEL_SAVE_JOB_ACTION],
            card: validCard(),
          }),
        );
      },
    );

    const {container} = renderChat({loadHistory, sendTurn, resumeRun});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'paste a long jd');

    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-jd-confirmation-card'),
      ).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('jobagent-jd-confirmation-card')).toHaveLength(
      1,
    );
    expect(screen.getByText(JD_CONFIRMATION_HEADING)).toBeInTheDocument();
    expect(screen.getByText(JD_CONFIRMATION_SENTENCE)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: SAVE_JOB_LABEL})).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
    ).toBeInTheDocument();
    expect(screen.getByText(REVIEW_JD_LABEL)).toBeInTheDocument();
    expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
      'false',
    );
    expect(resumeRun).not.toHaveBeenCalled();
    // No raw payload leakage
    expect(container.textContent).not.toMatch(/message_id|raw_content|tc-save/);
  });

  it('reconstructs exactly one card after history/restart hydration', async () => {
    const loadHistory = vi.fn().mockResolvedValue(interruptedHistory());
    const resumeRun = vi.fn();
    const {container} = renderChat({
      loadHistory,
      sendTurn: vi.fn(),
      resumeRun,
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-jd-confirmation-card'),
      ).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('jobagent-jd-confirmation-card')).toHaveLength(
      1,
    );
    expect(screen.getByText(REVIEW_JD_LABEL)).toBeInTheDocument();
    expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
      'false',
    );
    expect(resumeRun).not.toHaveBeenCalled();
  });

  it('falls back to generic interrupted notice for malformed projection', async () => {
    const loadHistory = vi
      .fn()
      .mockResolvedValue(interruptedHistory(validPending({text: 'LEAK'})));
    const {container} = renderChat({
      loadHistory,
      sendTurn: vi.fn(),
      resumeRun: vi.fn(),
    });

    await waitFor(() => {
      expect(screen.getByText('Run interrupted')).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId('jobagent-jd-confirmation-card'),
    ).not.toBeInTheDocument();
    expect(container.textContent).not.toContain('LEAK');
    expect(container.textContent).not.toMatch(/"kind"|allowed_actions/);
    expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
      'false',
    );
  });
});

describe('Resume lock and branch gating', () => {
  it('locks both buttons on first click and resumes once via shared endpoint', async () => {
    let resolveResume: (() => void) | null = null;
    const resumeRun = vi.fn(
      async (
        runId: string,
        action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        expect(runId).toBe(RUN_ID);
        expect(action).toBe(SAVE_JOB_ACTION);
        await new Promise<void>((resolve) => {
          resolveResume = resolve;
        });
        cbs.onEvent(
          sse(EVENT_C, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_D, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-save-jd-1',
            tool_name: 'save_job',
            status: 'completed',
            duration_ms: 20,
            summary: 'Saved',
          }),
        );
        cbs.onEvent(sse(EVENT_E, 'run_completed', {state: 'completed'}));
      },
    );
    const loadHistory = vi
      .fn()
      .mockResolvedValueOnce(interruptedHistory())
      .mockResolvedValue(terminalCommittedHistory());

    const {container} = renderChat({
      loadHistory,
      sendTurn: vi.fn(),
      resumeRun,
    });
    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: SAVE_JOB_LABEL}),
      ).toBeInTheDocument();
    });

    const save = screen.getByRole('button', {name: SAVE_JOB_LABEL});
    const cancel = screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL});
    await userEvent.click(save);
    await userEvent.click(save);
    await userEvent.click(cancel);

    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    expect(resumeRun.mock.calls[0]![1]).toBe(SAVE_JOB_ACTION);

    await waitFor(() => {
      expect(screen.getByRole('button', {name: SAVE_JOB_LABEL})).toBeDisabled();
      expect(
        screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
      ).toBeDisabled();
    });

    await act(async () => {
      resolveResume?.();
    });
    void container;
  });

  it('keeps both buttons locked after ambiguous transport failure', async () => {
    const resumeRun = vi.fn(async () => {
      const {ChatApiError} = await import('../lib/api/chat');
      throw new ChatApiError(0, 'STREAM_ERROR', 'Resume transport failed');
    });
    const loadHistory = vi.fn().mockResolvedValue(interruptedHistory());
    const {container} = renderChat({
      loadHistory,
      sendTurn: vi.fn(),
      resumeRun,
    });
    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: SAVE_JOB_LABEL}),
      ).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', {name: SAVE_JOB_LABEL}));
    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByRole('button', {name: SAVE_JOB_LABEL})).toBeDisabled();
      expect(
        screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
      ).toBeDisabled();
    });
    // Still locked after second attempt attempt is ignored
    await userEvent.click(
      screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
    );
    expect(resumeRun).toHaveBeenCalledTimes(1);
    void container;
  });

  it('cancel completes with no SavedJobCard, no invalidation, no evaluate', async () => {
    const onInvalidated = vi.fn();
    const resumeRun = vi.fn(
      async (
        _runId: string,
        action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        expect(action).toBe(CANCEL_SAVE_JOB_ACTION);
        cbs.onEvent(
          sse(EVENT_C, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_D, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-save-jd-1',
            tool_name: 'save_job',
            status: 'completed',
            duration_ms: 5,
            summary: 'JD chưa được lưu',
          }),
        );
        cbs.onEvent(sse(EVENT_E, 'run_completed', {state: 'completed'}));
      },
    );
    const loadHistory = vi
      .fn()
      .mockResolvedValueOnce(interruptedHistory())
      .mockResolvedValue(terminalCancelledHistory());

    renderChat(
      {loadHistory, sendTurn: vi.fn(), resumeRun},
      {onSavedJobsInvalidated: onInvalidated},
    );
    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
      ).toBeInTheDocument();
    });
    await userEvent.click(
      screen.getByRole('button', {name: CANCEL_SAVE_JOB_LABEL}),
    );
    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(
        screen.queryByTestId('jobagent-jd-confirmation-card'),
      ).not.toBeInTheDocument();
    });
    // Cancellation result is not a SavedJobCard projection
    expect(screen.queryByTestId('jobagent-saved-job-card')).not.toBeInTheDocument();
    await waitFor(() => {
      // rehydrate may complete; still no invalidation
      expect(loadHistory.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    expect(onInvalidated).not.toHaveBeenCalled();
  });

  it('save invalidates exactly once only after durable committed rehydrate', async () => {
    const onInvalidated = vi.fn();
    const resumeRun = vi.fn(
      async (
        _runId: string,
        action: string,
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        expect(action).toBe(SAVE_JOB_ACTION);
        cbs.onEvent(
          sse(EVENT_C, 'run_started', {state: 'running', resumed: true}),
        );
        cbs.onEvent(
          sse(EVENT_D, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc-save-jd-1',
            tool_name: 'save_job',
            status: 'completed',
            duration_ms: 30,
            summary: 'Saved job description',
          }),
        );
        cbs.onEvent(sse(EVENT_E, 'run_completed', {state: 'completed'}));
      },
    );
    const loadHistory = vi
      .fn()
      .mockResolvedValueOnce(interruptedHistory())
      .mockResolvedValue(terminalCommittedHistory());

    renderChat(
      {loadHistory, sendTurn: vi.fn(), resumeRun},
      {onSavedJobsInvalidated: onInvalidated},
    );
    await waitFor(() => {
      expect(
        screen.getByRole('button', {name: SAVE_JOB_LABEL}),
      ).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', {name: SAVE_JOB_LABEL}));
    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onInvalidated).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-saved-job-card')).toBeInTheDocument();
    });
    // No second invalidation on further rehydrate of same committed run
    expect(onInvalidated).toHaveBeenCalledTimes(1);
  });
});

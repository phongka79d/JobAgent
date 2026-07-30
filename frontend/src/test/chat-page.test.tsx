/**
 * Chat page UI tests: history, stream, tool activity, lock, failure states (04B).
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
import type {StreamCallbacks, TurnRequest} from '../lib/api/chat';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const EVENT_C = '33333333-3333-4333-8333-333333333333';
const EVENT_D = '44444444-4444-4444-8444-444444444444';
const EVENT_E = '55555555-5555-4555-8555-555555555555';
const EVENT_F = '66666666-6666-4666-8666-666666666666';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const MSG_OLD = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const TS = '2026-07-13T12:00:00.000Z';
const TS_NEW = '2026-07-13T12:00:01.000Z';
const TS_OLD = '2026-07-13T11:00:00.000Z';
const CONVERSATION_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const ATTACHMENT_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';

/** Capture IntersectionObserver instances so load-older can be fired in tests. */
type IoCallback = IntersectionObserverCallback;
type FakeIo = IntersectionObserver & {
  trigger: (isIntersecting?: boolean) => void;
};
const ioInstances: FakeIo[] = [];

beforeEach(() => {
  ioInstances.length = 0;
  class FakeIntersectionObserver implements IntersectionObserver {
    readonly root: Element | Document | null = null;
    readonly rootMargin = '';
    readonly thresholds: readonly number[] = [];
    private readonly cb: IoCallback;
    private target: Element | null = null;
    constructor(cb: IoCallback) {
      this.cb = cb;
      const self = this as unknown as FakeIo;
      self.trigger = (isIntersecting = true) => {
        if (!this.target) {
          return;
        }
        this.cb(
          [
            {
              isIntersecting,
              target: this.target,
              intersectionRatio: isIntersecting ? 1 : 0,
              time: 0,
              boundingClientRect: {} as DOMRectReadOnly,
              intersectionRect: {} as DOMRectReadOnly,
              rootBounds: null,
            },
          ],
          this,
        );
      };
      ioInstances.push(self);
    }
    observe(target: Element): void {
      this.target = target;
      // Do not auto-fire — tests call trigger() when exercising load-older.
    }
    unobserve(): void {
      this.target = null;
    }
    disconnect(): void {
      this.target = null;
    }
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function emptyHistory(): HistoryPage {
  return {items: [], next_cursor: null};
}

/**
 * Durable history keeps the run on the initiating user message while
 * ChatMessages projects its backend-owned activity onto the assistant row.
 */
function historyWithMessages(): HistoryPage {
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Hello from history',
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
          activities: [
            {
              activity_id: TOOL_EXEC,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'tool',
              label: 'Check lookup availability',
              technical_name: 'lookup_status',
              state: 'completed',
              started_at: TS,
              updated_at: TS,
              completed_at: TS,
              duration_ms: 42,
              error_code: null,
            },
          ],
          tool_executions: [
            {
              id: TOOL_EXEC,
              tool_call_id: 'tc-history-1',
              tool_name: 'lookup_status',
              status: 'completed',
              duration_ms: 42,
              error_code: null,
              result: {
                ok: true,
                code: null,
                summary: 'ok short',
                data: null,
              },
              arguments_summary: null,
              created_at: TS,
              updated_at: TS,
            },
          ],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'History assistant reply',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: 'cursor-older',
  };
}

function historyWithRunningUserOnly(): HistoryPage {
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Reloaded while the Agent was working',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'running',
          pending_approval: null,
          error_code: null,
          completed_at: null,
          created_at: TS,
          updated_at: TS,
          activities: [
            {
              activity_id: EVENT_A,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'assistant',
              label: 'Generating reply',
              technical_name: 'response_generation',
              state: 'running',
              started_at: TS,
              updated_at: TS,
              completed_at: null,
              duration_ms: null,
              error_code: null,
            },
          ],
          tool_executions: [],
        },
      },
    ],
    next_cursor: null,
  };
}

function historyWithFailedUserOnly(): HistoryPage {
  const page = historyWithRunningUserOnly();
  const run = page.items[0]?.run;
  const activity = run?.activities[0];
  if (!run || !activity) {
    throw new Error('running history fixture is incomplete');
  }
  run.state = 'failed';
  run.error_code = 'AGENT_EXECUTION_FAILED';
  run.completed_at = TS_NEW;
  activity.state = 'failed';
  activity.updated_at = TS_NEW;
  activity.completed_at = TS_NEW;
  activity.duration_ms = 11600;
  activity.error_code = 'AGENT_EXECUTION_FAILED';
  return page;
}

function olderHistoryPage(): HistoryPage {
  return {
    items: [
      {
        id: MSG_OLD,
        role: 'user',
        content: 'Older message',
        structured_payload: null,
        created_at: TS_OLD,
        updated_at: TS_OLD,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function sse(
  eventId: string,
  event: SseEvent['event'],
  payload: SseEvent['payload'],
): SseEvent {
  return {
    event_id: eventId,
    run_id: RUN_ID,
    timestamp: TS,
    event,
    payload,
  } as SseEvent;
}

function renderChat(deps: ChatPageDeps) {
  return render(
    <Theme theme={neutralTheme}>
      <ChatPage deps={deps} />
    </Theme>,
  );
}

describe('pending profile composer gating', () => {
  it('blocks ordinary turns while extraction is awaiting or failed', async () => {
    for (const setupStatus of [
      'awaiting_extraction',
      'extraction_failed',
    ] as const) {
      const view = render(
        <Theme theme={neutralTheme}>
          <ChatPage
            conversationId={CONVERSATION_ID}
            selectedProfileState="pending"
            selectedProfileSetupStatus={setupStatus}
            deps={{
              loadConversationHistory: vi.fn().mockResolvedValue(emptyHistory()),
            }}
          />
        </Theme>,
      );

      await waitFor(() => {
        expect(
          getComposerEditable(view.container).getAttribute('contenteditable'),
        ).toBe('false');
      });
      view.unmount();
    }
  });

  it('blocks ordinary turns while allowing the owned automatic extraction turn', async () => {
    const loadConversationHistory = vi.fn().mockResolvedValue(emptyHistory());
    const sendConversationTurn = vi.fn().mockResolvedValue(undefined);
    const {container} = render(
      <Theme theme={neutralTheme}>
        <ChatPage
          conversationId={CONVERSATION_ID}
          selectedProfileState="pending"
          selectedProfileSetupStatus="awaiting_extraction"
          sidebarAttachmentTurn={{
            requestKey: 1,
            attachmentId: ATTACHMENT_ID,
            message: 'Extract the uploaded CV.',
          }}
          deps={{loadConversationHistory, sendConversationTurn}}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
        'false',
      );
    });
    await waitFor(() => expect(sendConversationTurn).toHaveBeenCalledTimes(1));
    expect(sendConversationTurn.mock.calls[0]?.[0]).toBe(CONVERSATION_ID);
    expect(sendConversationTurn.mock.calls[0]?.[1]).toMatchObject({
      attachment_ids: [ATTACHMENT_ID],
    });
  });

  it('enables draft-correction turns while awaiting approval', async () => {
    const {container} = render(
      <Theme theme={neutralTheme}>
        <ChatPage
          conversationId={CONVERSATION_ID}
          selectedProfileState="pending"
          selectedProfileSetupStatus="awaiting_approval"
          deps={{
            loadConversationHistory: vi.fn().mockResolvedValue(emptyHistory()),
          }}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
        'true',
      );
    });
  });
});

/** ChatComposer uses a contentEditable surface (not a native textarea). */
function getComposerEditable(container: HTMLElement): HTMLElement {
  // When isDisabled, Astryx sets contenteditable="false" but keeps role=textbox.
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
  // Wait until controlled draft enables Send, then click it.
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

describe('ChatPage history and load-older', () => {
  it('loads chronological history and renders backend activity', async () => {
    const loadHistory = vi.fn().mockResolvedValueOnce(historyWithMessages());
    const firstMount = renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getByText('Hello from history')).toBeInTheDocument();
    });
    expect(screen.getByText('History assistant reply')).toBeInTheDocument();
    expect(screen.getByText('Completed · 1 step')).toBeInTheDocument();
    expect(screen.getByText('Check lookup availability')).toBeInTheDocument();
    expect(screen.getByText('Check lookup availability')).toBeInTheDocument();
    expect(screen.getAllByText('Complete').length).toBeGreaterThan(0);
    expect(screen.queryByText(/lookup_status|42ms/)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: /Completed · 1 step/i}),
    ).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('ok short')).not.toBeInTheDocument();
    expect(loadHistory).toHaveBeenCalledWith(
      {limit: 50},
      expect.any(AbortSignal),
    );

    firstMount.unmount();
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(historyWithMessages()),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getByText('History assistant reply')).toBeInTheDocument();
    });
    expect(
      screen.getByRole('button', {name: /Completed · 1 step/i}),
    ).toHaveAttribute('aria-expanded', 'false');
    expect(
      screen.getByText('Check lookup availability'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/lookup_status|42ms/)).not.toBeInTheDocument();
  });

  it('shows disconnected activity when reload history ends with a running user run', async () => {
    const user = userEvent.setup();
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(historyWithRunningUserOnly()),
      sendTurn: vi.fn(),
    });

    await waitFor(() => {
      expect(
        screen.getByText('Connection lost. Your request may still be running.'),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/^Completed ·/)).not.toBeInTheDocument();

    const disclosure = screen.getByRole('button', {
      name: /Connection lost\. Your request may still be running\./i,
    });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');

    await user.click(disclosure);
    expect(screen.getByText('Generating reply')).toBeInTheDocument();
    expect(screen.getByText('In progress')).toBeInTheDocument();
    expect(screen.queryByText(/response_generation/)).not.toBeInTheDocument();
  });

  it('shows failed activity when reload history ends without an assistant message', async () => {
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(historyWithFailedUserOnly()),
      sendTurn: vi.fn(),
    });

    await waitFor(() => {
      expect(screen.getByText('Unable to complete · 1 step')).toBeInTheDocument();
    });
    expect(screen.queryByText(/^Completed ·/)).not.toBeInTheDocument();
  });

  it('renders durable failed tool status text without complete/error aliases', async () => {
    const failedToolHistory: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'Try a tool',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: {
            id: RUN_ID,
            user_message_id: MSG_USER,
            state: 'failed',
            pending_approval: null,
            error_code: 'TOOL_ERROR',
            completed_at: TS,
            created_at: TS,
            updated_at: TS,
            activities: [
              {
                activity_id: TOOL_EXEC,
                run_id: RUN_ID,
                sequence: 0,
                kind: 'tool',
                label: 'Check lookup availability',
                technical_name: 'lookup_status',
                state: 'failed',
                started_at: TS,
                updated_at: TS,
                completed_at: TS,
                duration_ms: 11,
                error_code: 'TOOL_ERROR',
              },
            ],
            tool_executions: [
              {
                id: TOOL_EXEC,
                tool_call_id: 'tc-fail-1',
                tool_name: 'lookup_status',
                status: 'failed',
                duration_ms: 11,
                error_code: 'TOOL_ERROR',
                result: {
                  ok: false,
                  code: 'TOOL_ERROR',
                  summary: 'lookup failed durably',
                  data: null,
                },
                arguments_summary: null,
                created_at: TS,
                updated_at: TS,
              },
            ],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'Could not complete the lookup.',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    const loadHistory = vi.fn().mockResolvedValueOnce(failedToolHistory);
    renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getByText('Try a tool')).toBeInTheDocument();
    });
    expect(screen.getByText('Unable to complete · 1 step')).toBeInTheDocument();
    expect(screen.getByText('Check lookup availability')).toBeInTheDocument();
    expect(screen.getByText('Could not complete')).toBeInTheDocument();
    expect(screen.queryByText(/lookup_status|11ms|TOOL_ERROR/)).not.toBeInTheDocument();
    expect(screen.queryByText('lookup failed durably')).not.toBeInTheDocument();
    expect(screen.queryByText(/^complete$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^error$/)).not.toBeInTheDocument();
  });

  it('loads older pages by next_cursor via scroll-to-top action', async () => {
    const loadHistory = vi
      .fn()
      .mockResolvedValueOnce(historyWithMessages())
      .mockResolvedValueOnce(olderHistoryPage());

    renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getByText('Hello from history')).toBeInTheDocument();
    });

    // Wait for ChatMessageList to register an IntersectionObserver sentinel.
    await waitFor(() => {
      expect(ioInstances.length).toBeGreaterThan(0);
    });

    await act(async () => {
      for (const io of ioInstances) {
        io.trigger(true);
      }
    });

    await waitFor(() => {
      expect(loadHistory).toHaveBeenCalledWith({
        limit: 50,
        before: 'cursor-older',
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Older message')).toBeInTheDocument();
    });
  });
});

describe('ChatPage send / stream / lock', () => {
  it('sends a turn, streams text once, and unlocks after completion', async () => {
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
        cbs.onEvent(sse(EVENT_B, 'text_delta', {delta: 'Hello '}));
        cbs.onEvent(sse(EVENT_C, 'text_delta', {delta: 'world'}));
        cbs.onEvent(sse(EVENT_D, 'run_completed', {state: 'completed'}));
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});

    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    await submitMessage(container, 'Hi there');

    await waitFor(() => {
      expect(sendTurn).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText('Hi there')).toBeInTheDocument();
      expect(screen.getByText('Hello world')).toBeInTheDocument();
    });

    await waitFor(() => {
      const editable = getComposerEditable(container);
      expect(editable.getAttribute('contenteditable')).toBe('true');
    });
  });

  it('captures the selected Job UUID when a turn is sent', async () => {
    const selectedAtSend = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
    const selectedAfterSend = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
    let finish: (() => void) | null = null;
    const sendTurn = vi.fn(
      async (
        _body: TurnRequest,
        callbacks: StreamCallbacks,
      ) => {
        await new Promise<void>((resolve) => {
          finish = () => {
            callbacks.onEvent(
              sse(EVENT_D, 'run_completed', {state: 'completed'}),
            );
            resolve();
          };
        });
      },
    );
    const view = render(
      <Theme theme={neutralTheme}>
        <ChatPage
          selectedJobId={selectedAtSend}
          deps={{loadHistory: vi.fn().mockResolvedValue(emptyHistory()), sendTurn}}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(view.container, 'Tailor this');
    await waitFor(() => expect(sendTurn).toHaveBeenCalledTimes(1));

    view.rerender(
      <Theme theme={neutralTheme}>
        <ChatPage
          selectedJobId={selectedAfterSend}
          deps={{loadHistory: vi.fn().mockResolvedValue(emptyHistory()), sendTurn}}
        />
      </Theme>,
    );
    expect(sendTurn.mock.calls[0]?.[0]).toMatchObject({
      selected_job_id: selectedAtSend,
    });
    await act(async () => finish?.());
  });

  it('disables composer while streaming and shows exact tool activity', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    let resolveStream: (() => void) | null = null;
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
            tool_call_id: 'tc1',
            tool_name: 'synthetic_tool',
            status: 'running',
            duration_ms: null,
            summary: null,
            error_code: null,
            activity: {
              activity_id: TOOL_EXEC,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'tool',
              label: 'Use synthetic tool',
              technical_name: 'synthetic_tool',
              state: 'running',
              started_at: TS,
              updated_at: TS,
              completed_at: null,
              duration_ms: null,
              error_code: null,
            },
          }),
        );
        await new Promise<void>((resolve) => {
          resolveStream = resolve;
        });
        cbs.onEvent(
          sse(EVENT_C, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc1',
            tool_name: 'synthetic_tool',
            status: 'completed',
            duration_ms: 120,
            summary: 'done',
            error_code: null,
            activity: {
              activity_id: TOOL_EXEC,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'tool',
              label: 'Use synthetic tool',
              technical_name: 'synthetic_tool',
              state: 'completed',
              started_at: TS,
              updated_at: TS_NEW,
              completed_at: TS_NEW,
              duration_ms: 120,
              error_code: null,
            },
          }),
        );
        cbs.onEvent(sse(EVENT_D, 'text_delta', {delta: 'After tools'}));
        cbs.onEvent(sse(EVENT_E, 'run_completed', {state: 'completed'}));
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    await submitMessage(container, 'Run tool');

    await waitFor(() => {
      const current = screen
        .getAllByText('Use synthetic tool')
        .find((element) => element.getAttribute('aria-live') === 'polite');
      expect(current).toBeInTheDocument();
      expect(screen.getByText('In progress')).toBeInTheDocument();
      expect(screen.queryByText(/synthetic_tool/)).not.toBeInTheDocument();
      expect(screen.queryByText('…')).not.toBeInTheDocument();
    });
    // In-flight: contentEditable disabled via isDisabled on ChatComposer.
    await waitFor(() => {
      const field = getComposerEditable(container);
      expect(field.getAttribute('contenteditable')).toBe('false');
    });
    // Send remains unavailable while streaming.
    expect(
      within(container)
        .getAllByRole('button', {name: 'Send'})
        .every((b) => (b as HTMLButtonElement).disabled),
    ).toBe(true);

    await act(async () => {
      resolveStream?.();
    });

    await waitFor(() => {
      expect(screen.getByText('After tools')).toBeInTheDocument();
      expect(screen.getByText('Completed · 1 step')).toBeInTheDocument();
      expect(screen.getByText('Complete')).toBeInTheDocument();
      expect(screen.queryByText(/synthetic_tool|120ms/)).not.toBeInTheDocument();
      expect(screen.queryByText('done')).not.toBeInTheDocument();
    });
  });

  it('deduplicates repeated event_id in the UI stream', async () => {
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
        const delta = sse(EVENT_B, 'text_delta', {delta: 'Once'});
        cbs.onEvent(delta);
        cbs.onEvent(delta);
        cbs.onEvent(sse(EVENT_C, 'run_completed', {state: 'completed'}));
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    await submitMessage(container, 'dup');

    await waitFor(() => {
      expect(screen.getByText('Once')).toBeInTheDocument();
    });
    expect(screen.queryByText('OnceOnce')).not.toBeInTheDocument();
  });
});

describe('ChatPage failure / disconnect / interrupted visibility', () => {
  it('shows failed stream state without false completion', async () => {
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
          sse(EVENT_B, 'assistant_status', {
            message: 'Generate response',
            activity: {
              activity_id: EVENT_F,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'assistant',
              label: 'Generate response',
              technical_name: 'response_generation',
              state: 'running',
              started_at: TS,
              updated_at: TS,
              completed_at: null,
              duration_ms: null,
              error_code: null,
            },
          }),
        );
        cbs.onEvent(
          sse(EVENT_C, 'assistant_status', {
            message: 'Generate response',
            activity: {
              activity_id: EVENT_F,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'assistant',
              label: 'Generate response',
              technical_name: 'response_generation',
              state: 'failed',
              started_at: TS,
              updated_at: TS_NEW,
              completed_at: TS_NEW,
              duration_ms: 1000,
              error_code: 'PROVIDER_TIMEOUT',
            },
          }),
        );
        cbs.onEvent(
          sse(EVENT_D, 'run_failed', {
            state: 'failed',
            error_code: 'PROVIDER_TIMEOUT',
            summary: 'Provider timed out',
          }),
        );
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    await submitMessage(container, 'fail');

    await waitFor(() => {
      expect(screen.getByText('Unable to complete · 1 step')).toBeInTheDocument();
      expect(
        screen.getByText('Could not complete'),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/response_generation|PROVIDER_TIMEOUT|1s/),
      ).not.toBeInTheDocument();
    });
    expect(screen.queryByText('Run completed')).not.toBeInTheDocument();
  });

  it('shows disconnected state as non-complete', async () => {
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
        cbs.onEvent(sse(EVENT_B, 'text_delta', {delta: 'Partial'}));
        cbs.onDisconnected?.();
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    await submitMessage(container, 'cut');

    await waitFor(() => {
      // Notice appears in ChatSystemMessage and composer status (both intentional).
      expect(
        screen.getAllByText(/Stream disconnected — run is not completed/)
          .length,
      ).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Partial')).toBeInTheDocument();
    });
    // Disconnect never surfaces false success / completed run chrome.
    expect(screen.queryByText('Run completed')).not.toBeInTheDocument();
    expect(screen.queryByText(/^completed$/)).not.toBeInTheDocument();
  });

  it('disconnect mid-tool leaves exact running status and never completed', async () => {
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
            tool_call_id: 'tc-disconnect',
            tool_name: 'lookup_status',
            status: 'running',
            duration_ms: null,
            summary: null,
            error_code: null,
            activity: {
              activity_id: TOOL_EXEC,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'tool',
              label: 'Check lookup availability',
              technical_name: 'lookup_status',
              state: 'running',
              started_at: TS,
              updated_at: TS,
              completed_at: null,
              duration_ms: null,
              error_code: null,
            },
          }),
        );
        cbs.onDisconnected?.();
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'disconnect tools');

    await waitFor(() => {
      expect(
        screen.getByText('Connection lost. Your request may still be running.'),
      ).toBeInTheDocument();
      expect(screen.getByText('Check lookup availability')).toBeInTheDocument();
      expect(screen.getByText('In progress')).toBeInTheDocument();
      expect(screen.queryByText(/lookup_status/)).not.toBeInTheDocument();
    });
    expect(screen.queryByText('Run completed')).not.toBeInTheDocument();
    expect(screen.queryByText(/^completed$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^failed$/)).not.toBeInTheDocument();
  });

  it('shows interrupted state and locks the composer without approval cards for non-profile kinds', async () => {
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
          sse(EVENT_B, 'assistant_status', {
            message: 'Prepare confirmation',
            activity: {
              activity_id: EVENT_E,
              run_id: RUN_ID,
              sequence: 0,
              kind: 'assistant',
              label: 'Prepare confirmation',
              technical_name: 'response_generation',
              state: 'running',
              started_at: TS,
              updated_at: TS,
              completed_at: null,
              duration_ms: null,
              error_code: null,
            },
          }),
        );
        cbs.onEvent(
          sse(EVENT_F, 'approval_required', {
            state: 'interrupted',
            kind: 'confirm',
            allowed_actions: ['approve', 'reject'],
            card: {},
          }),
        );
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    await submitMessage(container, 'interrupt');

    await waitFor(() => {
      const summary = screen.getByText(
        'Waiting for your confirmation · 1 step',
      );
      expect(summary).toHaveAttribute('data-running', 'false');
      expect(
        screen.getByLabelText('Waiting for your confirmation · 1 step'),
      ).toHaveAttribute('data-variant', 'warning');
      expect(
        screen.getByText('Run interrupted — new turns are blocked until resumed'),
      ).toBeInTheDocument();
      expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
        'false',
      );
    });
    // Non-profile_commit interrupts never render Save Profile / Request Changes.
    expect(screen.queryByRole('button', {name: /approve/i})).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: 'Save Profile'}),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: 'Request Changes'}),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-approval-card')).not.toBeInTheDocument();
  });
});

describe('App shell hosts chat layout', () => {
  it('renders AppShell with chat page through public Astryx composition', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const {container} = render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [
                  {
                    id: '11111111-1111-4111-8111-111111111111',
                    display_name: 'Synthetic CV',
                    cv_filename: 'synthetic.pdf',
                    attachment_state: 'active',
                    location: null,
                    skill_tags: [],
                    skill_count: 0,
                    extraction_version: 'v1',
                    source_hash: 'hash',
                    state: 'ready',
                    setup_status: null,
                    is_active: true,
                    created_at: TS,
                    updated_at: TS,
                    last_opened_at: TS,
                  },
                ],
                active_profile_id: '11111111-1111-4111-8111-111111111111',
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [
                  {
                    id: CONVERSATION_ID,
                    profile_id: '11111111-1111-4111-8111-111111111111',
                    title: 'Chat',
                    created_at: TS,
                    updated_at: TS,
                    last_opened_at: TS,
                    is_selected: true,
                  },
                ],
                next_cursor: null,
              }),
            },
            chat: {loadConversationHistory: loadHistory},
          }}
        />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    expect(await screen.findByTestId('jobagent-chat-page')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
  });
});

describe('ChatPage no out-of-scope chrome', () => {
  it('does not render match or save-job UI on the chat page', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    renderChat({loadHistory, sendTurn: vi.fn()});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    expect(screen.queryByText(/match jobs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/save job/i)).not.toBeInTheDocument();
  });
});

describe('ChatPage PDF attachment token (04A)', () => {
  const ATTACH_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

  it('renders compact PDF token and submits attachment_ids only', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    const uploadCv = vi.fn().mockResolvedValue({
      attachment: {
        id: ATTACH_ID,
        original_name: 'chat-cv.pdf',
        mime_type: 'application/pdf',
        size_bytes: 100,
        page_count: 1,
        state: 'active',
        failure_code: null,
      },
      outcome: 'existing_active',
      profile: {
        present: true,
        profile_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        current_title: 'Engineer',
      },
      draft: null,
      bootstrap: null,
    });
    const sendTurn = vi.fn().mockResolvedValue(undefined);

    const {container} = renderChat({loadHistory, sendTurn, uploadCv});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });

    const file = new File(['%PDF-1.4'], 'chat-cv.pdf', {
      type: 'application/pdf',
    });
    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null;
    expect(input).not.toBeNull();
    await userEvent.upload(input!, file);

    await waitFor(() => {
      expect(uploadCv).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId('jobagent-chat-pdf-token')).toBeInTheDocument();
      expect(screen.getByText('chat-cv.pdf')).toBeInTheDocument();
    });

    await submitMessage(container, 'Please review my CV');

    await waitFor(() => {
      expect(sendTurn).toHaveBeenCalled();
    });
    const body = sendTurn.mock.calls[0]![0] as {
      message: string;
      attachment_ids?: string[];
    };
    expect(body.message).toBe('Please review my CV');
    expect(body.attachment_ids).toEqual([ATTACH_ID]);
    expect(JSON.stringify(body)).not.toMatch(/storage_path|%PDF/);
  });

  it('disables PDF attach while streaming', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    let resolveStream: (() => void) | null = null;
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        await new Promise<void>((resolve) => {
          resolveStream = resolve;
        });
        cbs.onEvent(sse(EVENT_B, 'run_completed', {state: 'completed'}));
      },
    );
    const uploadCv = vi.fn();

    const {container} = renderChat({loadHistory, sendTurn, uploadCv});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    await submitMessage(container, 'Streaming now');

    await waitFor(() => {
      const field = getComposerEditable(container);
      expect(field.getAttribute('contenteditable')).toBe('false');
    });

    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null;
    expect(input).not.toBeNull();
    expect(
      input!.disabled ||
        input!.getAttribute('aria-disabled') === 'true' ||
        input!.closest('[aria-disabled="true"]') !== null,
    ).toBe(true);

    await act(async () => {
      resolveStream?.();
    });
  });
});

describe('ChatPage active-CV source from durable history (03A)', () => {
  const CV_ATTACHMENT = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';

  function historyWithActiveCv(): HistoryPage {
    return {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'Tôi có mấy Certificate?',
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
            activities: [],
            tool_executions: [
              {
                id: TOOL_EXEC,
                tool_call_id: 'tc-cv-1',
                tool_name: 'read_active_cv',
                status: 'completed',
                duration_ms: 40,
                error_code: null,
                result: {
                  ok: true,
                  code: null,
                  summary: 'Read active CV page',
                  data: {
                    attachment_id: CV_ATTACHMENT,
                    extraction_version: 'v1',
                    source_hash: 'hash-abc',
                    mode: 'section',
                    returned_chars: 40,
                    truncated: false,
                    next_cursor: null,
                    records: [
                      {
                        kind: 'entry',
                        section_id: 'sec-certs',
                        entry_id: 'entry-1',
                        ordinal: 0,
                        title: 'AWS Certified',
                        subtitle: null,
                        date_text: '2024',
                        location: null,
                        body: 'Cloud practitioner certificate.',
                        bullets: ['Exam passed'],
                        source_chunk_ordinals: [0, 1],
                      },
                    ],
                  },
                },
                arguments_summary: null,
                created_at: TS,
                updated_at: TS,
              },
            ],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'Bạn có **1** Certificate.',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
  }

  it('hydrates history with one Source citation and exact dialog evidence', async () => {
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModal() {
        this.setAttribute('open', '');
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function close() {
        this.removeAttribute('open');
      };
    }

    const loadHistory = vi.fn().mockResolvedValueOnce(historyWithActiveCv());
    const user = userEvent.setup();
    renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getByText(/Bạn có/)).toBeInTheDocument();
    });
    // Markdown: raw ** not visible; citation present exactly once.
    expect(screen.queryByText(/\*\*1\*\*/)).not.toBeInTheDocument();
    const citations = screen.getAllByTestId('jobagent-active-cv-citation');
    expect(citations).toHaveLength(1);
    expect(citations[0]).toHaveTextContent('Source');

    await user.click(citations[0]);
    await waitFor(() => {
      expect(screen.getByText('Source from CV')).toBeInTheDocument();
    });
    expect(
      screen.getByText('Cloud practitioner certificate.'),
    ).toBeInTheDocument();
    expect(screen.getByText('AWS Certified')).toBeInTheDocument();
  });

  it('shows no citation for history without successful active-CV evidence', async () => {
    const loadHistory = vi.fn().mockResolvedValueOnce(historyWithMessages());
    renderChat({loadHistory, sendTurn: vi.fn()});
    await waitFor(() => {
      expect(screen.getByText('History assistant reply')).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId('jobagent-active-cv-citation'),
    ).not.toBeInTheDocument();
  });
});

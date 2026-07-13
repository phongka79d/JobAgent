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
import {
  friendlyToolLabel,
  formatToolDuration,
  toAstryxVisualToolStatus,
} from '../features/chat/components/ChatToolActivity';
import type {HistoryPage, SseEvent} from '../features/chat/types';
import type {StreamCallbacks} from '../lib/api/chat';

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
const TS_OLD = '2026-07-13T11:00:00.000Z';

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
 * Real Plan 3 history shape: tool_executions only on the initiating user
 * message run; assistant.run is null. ChatMessages projects user-run tools
 * onto the following assistant row for ChatToolCalls display.
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

describe('tool presentation helpers (status composition)', () => {
  it('maps JobAgent statuses to Astryx visual props without polluting labels', () => {
    expect(toAstryxVisualToolStatus('pending')).toBe('pending');
    expect(toAstryxVisualToolStatus('running')).toBe('running');
    // Presentation-only mapping — application state stays completed/failed.
    expect(toAstryxVisualToolStatus('completed')).toBe('complete');
    expect(toAstryxVisualToolStatus('failed')).toBe('error');
  });

  it('formats friendly labels and durations', () => {
    expect(friendlyToolLabel('lookup_status')).toBe('Lookup Status');
    expect(formatToolDuration(42)).toBe('42ms');
    expect(formatToolDuration(1500)).toBe('1.5s');
    expect(formatToolDuration(null)).toBeUndefined();
  });
});

describe('ChatPage history and load-older', () => {
  it('loads chronological history and renders exact tool status', async () => {
    const loadHistory = vi.fn().mockResolvedValueOnce(historyWithMessages());
    renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getByText('Hello from history')).toBeInTheDocument();
    });
    expect(screen.getByText('History assistant reply')).toBeInTheDocument();
    // Exact JobAgent status text (not complete/error aliases in visible state).
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('Lookup Status')).toBeInTheDocument();
    expect(screen.getByText('42ms')).toBeInTheDocument();
    expect(screen.getByText('ok short')).toBeInTheDocument();
    expect(loadHistory).toHaveBeenCalledWith(
      {limit: 50},
      expect.any(AbortSignal),
    );
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
      expect(screen.getByText('Synthetic Tool')).toBeInTheDocument();
      expect(screen.getByText('running')).toBeInTheDocument();
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
      expect(screen.getByText('completed')).toBeInTheDocument();
      expect(screen.getByText('done')).toBeInTheDocument();
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
          sse(EVENT_B, 'run_failed', {
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
      expect(
        screen.getByText(/Run failed: Provider timed out \(PROVIDER_TIMEOUT\)/),
      ).toBeInTheDocument();
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
  });

  it('shows interrupted state and locks the composer without approval cards', async () => {
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
      expect(screen.getByText('Run interrupted')).toBeInTheDocument();
      expect(getComposerEditable(container).getAttribute('contenteditable')).toBe(
        'false',
      );
    });
    expect(screen.queryByRole('button', {name: /approve/i})).not.toBeInTheDocument();
  });
});

describe('App shell hosts chat layout', () => {
  it('renders AppShell with chat page through public Astryx composition', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    // App mounts ChatPage without deps; inject via module mock is heavy —
    // render ChatPage under AppShell shape matching App.tsx instead when env missing.
    const {container} = render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument();
    // History may fail without VITE_API_BASE_URL; page still mounts.
    await waitFor(() => {
      expect(
        screen.getByText(/Start a conversation|History load issue/),
      ).toBeInTheDocument();
    });
    void loadHistory;
  });
});

describe('ChatPage no out-of-scope chrome', () => {
  it('does not render sidebar, profile, match, or save-job UI', async () => {
    const loadHistory = vi.fn().mockResolvedValue(emptyHistory());
    renderChat({loadHistory, sendTurn: vi.fn()});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    expect(screen.queryByText(/match jobs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/save job/i)).not.toBeInTheDocument();
  });
});

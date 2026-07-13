/**
 * Base Astryx conversation page over the Plan 3 history/SSE API path.
 * Single owner of UI dispatch into the (04A) chatReducer — no second store.
 */

import {useCallback, useEffect, useReducer, useRef, useState} from 'react';
import {
  ChatComposer,
  ChatLayout,
  ChatSystemMessage,
} from '@astryxdesign/core/Chat';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {VStack} from '@astryxdesign/core/VStack';

import {
  ChatApiError,
  fetchChatHistory,
  streamChatTurn,
  type StreamCallbacks,
} from '../../lib/api/chat';
import {ChatMessages} from './components/ChatMessages';
import {
  chatReducer,
  createInitialChatState,
  isComposerLocked,
} from './reducer';

export type ChatPageDeps = {
  loadHistory?: typeof fetchChatHistory;
  sendTurn?: typeof streamChatTurn;
};

export type ChatPageProps = {
  /** Injectable transport for tests; defaults to Plan 3 API client. */
  deps?: ChatPageDeps;
};

function newClientKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ChatPage({deps}: ChatPageProps) {
  const loadHistory = deps?.loadHistory ?? fetchChatHistory;
  const sendTurn = deps?.sendTurn ?? streamChatTurn;

  const [state, dispatch] = useReducer(
    chatReducer,
    undefined,
    createInitialChatState,
  );
  const [historyLoadError, setHistoryLoadError] = useState<string | null>(null);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const [draft, setDraft] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  /** Set true synchronously when a turn starts; cleared on terminal UI phases. */
  const inFlightRef = useRef(false);
  useEffect(() => {
    if (
      state.streamPhase === 'idle' ||
      state.streamPhase === 'failed' ||
      state.streamPhase === 'disconnected'
    ) {
      inFlightRef.current = false;
    } else if (
      state.streamPhase === 'connecting' ||
      state.streamPhase === 'streaming'
    ) {
      inFlightRef.current = true;
    }
  }, [state.streamPhase]);

  // Initial history hydration (newest page).
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    (async () => {
      try {
        const page = await loadHistory({limit: 50}, controller.signal);
        if (!cancelled) {
          dispatch({type: 'history/reset', page});
          setHistoryLoadError(null);
        }
      } catch (err) {
        if (cancelled || controller.signal.aborted) {
          return;
        }
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'Failed to load history';
        setHistoryLoadError(summary);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [loadHistory]);

  const nextCursorRef = useRef(state.nextCursor);
  nextCursorRef.current = state.nextCursor;
  const loadingOlderRef = useRef(false);

  const handleLoadOlder = useCallback(async () => {
    const cursor = nextCursorRef.current;
    if (!cursor || loadingOlderRef.current) {
      return;
    }
    loadingOlderRef.current = true;
    setIsLoadingOlder(true);
    try {
      const page = await loadHistory({
        limit: 50,
        before: cursor,
      });
      if (page && Array.isArray(page.items)) {
        dispatch({type: 'history/load_older', page});
      }
    } catch (err) {
      const summary =
        err instanceof ChatApiError
          ? err.summary
          : err instanceof Error
            ? err.message
            : 'Failed to load older messages';
      setHistoryLoadError(summary);
    } finally {
      loadingOlderRef.current = false;
      setIsLoadingOlder(false);
    }
  }, [loadHistory]);

  const handleSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (trimmed === '' || isComposerLocked(state)) {
        return;
      }

      setDraft('');
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const clientKey = newClientKey('user');
      // Mark in-flight before any async work so mid-stream disconnect is visible
      // even when React has not yet committed connecting/streaming phase.
      inFlightRef.current = true;
      dispatch({type: 'turn/start', clientKey, message: trimmed});

      const callbacks: StreamCallbacks = {
        onEvent: (event) => {
          dispatch({type: 'sse/event', event});
          if (
            event.event === 'run_completed' ||
            event.event === 'run_failed' ||
            event.event === 'approval_required'
          ) {
            inFlightRef.current = false;
          }
        },
        onMalformed: () => {
          // Malformed frames must not invent completion (reducer ignores via sse/raw).
        },
        onDisconnected: () => {
          // Visible non-complete: only while the turn is still in-flight.
          if (inFlightRef.current) {
            inFlightRef.current = false;
            dispatch({type: 'stream/disconnected'});
          }
        },
      };

      void (async () => {
        try {
          await sendTurn({message: trimmed}, callbacks, controller.signal);
        } catch (err) {
          if (controller.signal.aborted) {
            return;
          }
          if (err instanceof ChatApiError) {
            dispatch({
              type: 'stream/http_failed',
              code: err.code,
              summary: err.summary,
            });
            return;
          }
          dispatch({
            type: 'stream/http_failed',
            code: 'STREAM_ERROR',
            summary:
              err instanceof Error ? err.message : 'Stream failed unexpectedly',
          });
        }
      })();
    },
    [sendTurn, state],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const locked = isComposerLocked(state);
  const isStreaming =
    state.streamPhase === 'streaming' || state.streamPhase === 'connecting';
  const hasInterrupted = state.messages.some(
    (m) => m.run?.state === 'interrupted',
  );

  const composerStatus =
    state.streamPhase === 'failed' && state.streamError
      ? {
          type: 'warning' as const,
          message: `${state.streamError.summary} (${state.streamError.code})`,
        }
      : state.streamPhase === 'disconnected'
        ? {
            type: 'warning' as const,
            message: 'Stream disconnected — run is not completed',
          }
        : hasInterrupted
          ? {
              type: 'warning' as const,
              message: 'Run interrupted — new turns are blocked until resumed',
            }
          : undefined;

  const emptyState = (
    <EmptyState
      title="Start a conversation"
      description="Send a message to talk with JobAgent. History loads from the durable chat API."
      headingLevel={2}
      isCompact
    />
  );

  const hasListContent =
    state.messages.length > 0 ||
    state.streamPhase === 'failed' ||
    state.streamPhase === 'disconnected' ||
    state.streamPhase === 'connecting' ||
    state.streamPhase === 'streaming' ||
    state.assistantStatus !== null;

  // Only wire infinite-scroll when an older page exists (avoids empty mock hits in tests).
  const scrollToTopAction =
    state.nextCursor !== null && !isLoadingOlder
      ? async () => {
          await handleLoadOlder();
        }
      : undefined;

  return (
    <VStack
      gap={0}
      height="100%"
      width="100%"
      data-testid="jobagent-chat-page"
    >
      {historyLoadError ? (
        <ChatSystemMessage>
          {`History load issue: ${historyLoadError}`}
        </ChatSystemMessage>
      ) : null}
      <ChatLayout
        emptyState={emptyState}
        composer={
          <ChatComposer
            value={draft}
            onChange={setDraft}
            onSubmit={handleSubmit}
            isDisabled={locked}
            isStopShown={false}
            placeholder={
              locked
                ? hasInterrupted
                  ? 'Waiting for interrupt resolution…'
                  : 'Waiting for response…'
                : 'Message JobAgent…'
            }
            status={composerStatus}
            statusPosition="top"
          />
        }
      >
        {hasListContent ? (
          <ChatMessages
            messages={state.messages}
            streamPhase={state.streamPhase}
            streamError={state.streamError}
            assistantStatus={state.assistantStatus}
            onLoadOlder={scrollToTopAction}
            isStreaming={isStreaming}
          />
        ) : null}
      </ChatLayout>
    </VStack>
  );
}

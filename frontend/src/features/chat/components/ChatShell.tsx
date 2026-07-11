/**
 * Base Astryx chat shell: hydrates history, streams turns/resumes, maps pure state to UI.
 * Consumes 03B transport/reducer only — no direct provider/store access.
 */

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { Theme } from "@astryxdesign/core";
import { AppShell } from "@astryxdesign/core/AppShell";
import { Banner } from "@astryxdesign/core/Banner";
import { ChatLayout } from "@astryxdesign/core/Chat";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { VStack } from "@astryxdesign/core/VStack";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

import {
  fetchChatHistory,
  streamChatResume,
  streamChatTurn,
} from "../api";
import type { ChatSSEEvent, HistoryMessage } from "../contracts";
import {
  chatReducer,
  createInitialChatState,
  isSendDisabled,
  type ChatState,
} from "../reducer";
import { ChatComposerPanel } from "./ChatComposerPanel";
import { ChatMessages } from "./ChatMessages";

export interface ChatShellApi {
  readonly fetchHistory: typeof fetchChatHistory;
  readonly streamTurn: typeof streamChatTurn;
  readonly streamResume: typeof streamChatResume;
}

export interface ChatShellProps {
  /** Skip automatic history hydration (tests with deterministic state). */
  readonly skipHydrate?: boolean;
  /** Seed messages before/without network hydration. */
  readonly initialMessages?: readonly HistoryMessage[];
  /** Injectable transport for tests. */
  readonly api?: Partial<ChatShellApi>;
  /** Optional controlled initial reducer state for deterministic UI tests. */
  readonly initialState?: ChatState;
  /** When false, Theme wrapper is omitted (App already provides Theme). */
  readonly wrapTheme?: boolean;
}

function createIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

/**
 * Full-page chat experience: AppShell + ChatLayout + message/composer panels.
 */
export function ChatShell({
  skipHydrate = false,
  initialMessages,
  api: apiOverrides,
  initialState,
  wrapTheme = true,
}: ChatShellProps) {
  const fetchHistory = apiOverrides?.fetchHistory ?? fetchChatHistory;
  const streamTurn = apiOverrides?.streamTurn ?? streamChatTurn;
  const streamResume = apiOverrides?.streamResume ?? streamChatResume;

  const [state, dispatch] = useReducer(
    chatReducer,
    undefined,
    () =>
      initialState ??
      createInitialChatState({
        messages: initialMessages ? [...initialMessages] : [],
      }),
  );

  const [draft, setDraft] = useState("");
  const [hydrating, setHydrating] = useState(!skipHydrate && !initialState);
  const [hydrateError, setHydrateError] = useState<string | null>(null);
  const [resumeMode, setResumeMode] = useState<"approve" | "correct" | null>(
    null,
  );

  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  // Latest messages for optimistic append without stale closures.
  const messagesRef = useRef(state.messages);
  messagesRef.current = state.messages;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (skipHydrate || initialState) {
      setHydrating(false);
      return;
    }

    const controller = new AbortController();
    setHydrating(true);
    setHydrateError(null);

    void fetchHistory({ signal: controller.signal })
      .then((history) => {
        if (!mountedRef.current || controller.signal.aborted) {
          return;
        }
        dispatch({ type: "HYDRATE_HISTORY", messages: history.messages });
        setHydrating(false);
      })
      .catch((error: unknown) => {
        if (!mountedRef.current || controller.signal.aborted) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "Failed to load history";
        setHydrateError(message);
        setHydrating(false);
      });

    return () => {
      controller.abort();
    };
  }, [fetchHistory, skipHydrate, initialState]);

  const abortActiveStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const streamHandlers = useCallback(
    () => ({
      onEvent: (event: ChatSSEEvent) => {
        dispatch({ type: "SSE_EVENT", event });
      },
      onDisconnect: () => {
        dispatch({ type: "STREAM_DISCONNECTED" });
      },
      onAbort: () => {
        dispatch({ type: "STREAM_ABORTED" });
      },
      onError: (error: unknown) => {
        const message =
          error instanceof Error ? error.message : "Stream failed";
        dispatch({ type: "STREAM_ERROR", message });
      },
    }),
    [],
  );

  const runStream = useCallback(
    async (start: (signal: AbortSignal) => Promise<void>) => {
      abortActiveStream();
      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: "STREAM_OPEN" });

      try {
        await start(controller.signal);
      } catch {
        // onError already dispatched when the transport notifies.
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        if (mountedRef.current) {
          setResumeMode(null);
        }
      }
    },
    [abortActiveStream],
  );

  const handleSubmit = useCallback(
    (value: string) => {
      const text = value.trim();
      if (!text || isSendDisabled(state) || hydrating) {
        return;
      }

      const userMessage: HistoryMessage = {
        role: "user",
        content: text,
        created_at: nowIso(),
        structured_payload: null,
      };

      dispatch({
        type: "HYDRATE_HISTORY",
        messages: [...messagesRef.current, userMessage],
      });
      setDraft("");

      const idempotencyKey = createIdempotencyKey();
      void runStream(async (signal) => {
        await streamTurn(
          { text, idempotency_key: idempotencyKey },
          streamHandlers(),
          { signal },
        );
      });
    },
    [hydrating, runStream, state, streamHandlers, streamTurn],
  );

  const handleStop = useCallback(() => {
    abortActiveStream();
    dispatch({ type: "STREAM_ABORTED" });
  }, [abortActiveStream]);

  const handleResume = useCallback(
    (action: "approve" | "correct", correctionText?: string) => {
      if (!state.activeRunId || state.phase !== "awaiting_approval") {
        return;
      }
      if (resumeMode !== null) {
        return;
      }

      const trimmedCorrection =
        action === "correct" ? (correctionText ?? "").trim() : "";
      if (action === "correct" && trimmedCorrection.length === 0) {
        // Correct requires nonblank correction_text; ChatApproval gates the UI.
        return;
      }

      setResumeMode(action);
      const runId = state.activeRunId;
      const idempotencyKey = createIdempotencyKey();

      void runStream(async (signal) => {
        await streamResume(
          runId,
          {
            action,
            idempotency_key: idempotencyKey,
            correction_text: action === "correct" ? trimmedCorrection : null,
          },
          streamHandlers(),
          { signal },
        );
      });
    },
    [
      resumeMode,
      runStream,
      state.activeRunId,
      state.phase,
      streamHandlers,
      streamResume,
    ],
  );

  const sendDisabled =
    isSendDisabled(state) || hydrating || resumeMode !== null;
  const isStopShown = state.phase === "active";

  let composerStatus:
    | { type: "error" | "warning"; message?: string }
    | undefined;
  if (state.phase === "failed" && state.failure) {
    composerStatus = {
      type: "error",
      message:
        state.failure.message?.trim() ||
        `Run failed (${state.failure.errorCode})`,
    };
  } else if (state.phase === "disconnected") {
    composerStatus = {
      type: "warning",
      message: "Connection interrupted. Send again when ready.",
    };
  } else if (hydrateError) {
    composerStatus = {
      type: "error",
      message: "Could not load conversation history.",
    };
  }

  const emptyState = (
    <EmptyState
      title="Start a conversation"
      description="Ask JobAgent about your career workflow. Messages stream here with tool activity when the agent works."
      headingLevel={1}
      data-testid="chat-empty-state"
    />
  );

  const hasMessages =
    state.messages.length > 0 ||
    state.streamingText.length > 0 ||
    state.tools.length > 0 ||
    state.phase === "active" ||
    state.phase === "awaiting_approval" ||
    state.phase === "failed" ||
    state.phase === "disconnected" ||
    state.phase === "completed";

  const body = hydrating ? (
    <VStack gap={4} data-testid="chat-loading">
      <Spinner label="Loading conversation…" size="md" />
    </VStack>
  ) : (
    <ChatLayout
      density="balanced"
      emptyState={!hasMessages ? emptyState : undefined}
      composer={
        <ChatComposerPanel
          value={draft}
          onChange={setDraft}
          onSubmit={handleSubmit}
          onStop={handleStop}
          isDisabled={sendDisabled}
          isStopShown={isStopShown}
          status={composerStatus}
        />
      }
      data-testid="chat-layout"
    >
      {hasMessages ? (
        <ChatMessages
          messages={state.messages}
          phase={state.phase}
          streamingText={state.streamingText}
          tools={state.tools}
          assistantStatus={state.assistantStatus}
          assistantStatusMessage={state.assistantStatusMessage}
          approval={state.approval}
          failure={state.failure}
          streamError={state.streamError}
          approvalDisabled={
            resumeMode !== null || state.phase !== "awaiting_approval"
          }
          onApprove={() => {
            handleResume("approve");
          }}
          onCorrect={(correctionText) => {
            handleResume("correct", correctionText);
          }}
        />
      ) : null}
    </ChatLayout>
  );

  const shell = (
    <AppShell
      contentPadding={0}
      height="fill"
      variant="surface"
      banner={
        hydrateError ? (
          <Banner
            status="error"
            title="History unavailable"
            description="The chat shell is ready. Retry by reloading, or send a new message once the API is reachable."
            container="section"
            data-testid="chat-hydrate-banner"
          />
        ) : undefined
      }
      data-testid="chat-app-shell"
    >
      {body}
    </AppShell>
  );

  if (!wrapTheme) {
    return shell;
  }

  return (
    <Theme theme={neutralTheme} mode="system">
      {shell}
    </Theme>
  );
}

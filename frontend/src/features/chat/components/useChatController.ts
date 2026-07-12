/**
 * Chat transport controller: hydrate, turn/resume, sidebar CV turn, profile correction.
 */

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import {
  fetchChatHistory,
  streamChatResume,
  streamChatTurn,
} from "../api";
import type { HistoryMessage } from "../contracts";
import {
  chatReducer,
  createInitialChatState,
  isSendDisabled,
  type ChatState,
} from "../reducer";
import {
  resolveComposerStatus,
  resolveInteractionFlags,
  type PendingSidebarTurn,
} from "./chatControllerSupport";
import { useChatStream } from "./useChatStream";
import { useChatTurnActions } from "./useChatTurnActions";

export interface ChatShellApi {
  readonly fetchHistory: typeof fetchChatHistory;
  readonly streamTurn: typeof streamChatTurn;
  readonly streamResume: typeof streamChatResume;
}

export interface UseChatControllerOptions {
  readonly skipHydrate?: boolean;
  readonly initialMessages?: readonly HistoryMessage[];
  readonly api?: Partial<ChatShellApi>;
  readonly initialState?: ChatState;
  /** Called after a run reaches completed (e.g. refresh approved profile). */
  readonly onRunCompleted?: () => void;
}

export function useChatController({
  skipHydrate = false,
  initialMessages,
  api: apiOverrides,
  initialState,
  onRunCompleted,
}: UseChatControllerOptions = {}) {
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
  const [correctionMode, setCorrectionMode] = useState(false);
  const [focusRequestKey, setFocusRequestKey] = useState(0);
  const [pendingSidebarEpoch, setPendingSidebarEpoch] = useState(0);

  const messagesRef = useRef(state.messages);
  messagesRef.current = state.messages;
  const pendingSidebarQueueRef = useRef<PendingSidebarTurn[]>([]);
  const stateRef = useRef(state);
  stateRef.current = state;
  const hydratingRef = useRef(hydrating);
  hydratingRef.current = hydrating;
  const resumeModeRef = useRef(resumeMode);
  resumeModeRef.current = resumeMode;
  const correctionModeRef = useRef(correctionMode);
  correctionModeRef.current = correctionMode;

  const { markMounted, abortActiveStream, streamHandlers, runStream } =
    useChatStream(dispatch, onRunCompleted);

  useEffect(() => {
    markMounted(true);
    return () => {
      markMounted(false);
    };
  }, [markMounted]);

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
        if (controller.signal.aborted) {
          return;
        }
        dispatch({ type: "HYDRATE_HISTORY", messages: history.messages });
        setHydrating(false);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
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

  useEffect(() => {
    if (state.phase !== "awaiting_approval" && correctionMode) {
      setCorrectionMode(false);
    }
  }, [state.phase, correctionMode]);

  const {
    handleResume,
    handleSubmit,
    submitSidebarCvTurn,
    flushPendingSidebarQueue,
    handleStop,
  } = useChatTurnActions({
    dispatch,
    stateRef,
    messagesRef,
    hydratingRef,
    resumeModeRef,
    correctionModeRef,
    pendingSidebarQueueRef,
    setDraft,
    setResumeMode,
    setCorrectionMode,
    setPendingSidebarEpoch,
    streamTurn,
    streamResume,
    runStream,
    streamHandlers,
    abortActiveStream,
    activeRunId: state.activeRunId,
    phase: state.phase,
    resumeMode,
  });

  useEffect(() => {
    flushPendingSidebarQueue();
  }, [
    flushPendingSidebarQueue,
    hydrating,
    pendingSidebarEpoch,
    resumeMode,
    state.phase,
  ]);

  const enterCorrectionMode = useCallback(() => {
    if (state.phase !== "awaiting_approval" || resumeMode !== null) {
      return;
    }
    setCorrectionMode(true);
    setFocusRequestKey((n) => n + 1);
  }, [resumeMode, state.phase]);

  const isStopShown = state.phase === "active";
  const composerStatus = resolveComposerStatus(state, hydrateError);
  const { sendDisabled, approvalDisabled, composerPlaceholder } =
    resolveInteractionFlags({
      phase: state.phase,
      hydrating,
      resumeMode,
      correctionMode,
      sendBlockedByPhase: isSendDisabled(state),
    });

  return {
    state,
    draft,
    setDraft,
    hydrating,
    hydrateError,
    resumeMode,
    correctionMode,
    focusRequestKey,
    sendDisabled,
    isStopShown,
    composerStatus,
    composerPlaceholder,
    approvalDisabled,
    handleSubmit,
    handleStop,
    handleResume,
    enterCorrectionMode,
    submitSidebarCvTurn,
  };
}

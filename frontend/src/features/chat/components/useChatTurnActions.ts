/**
 * Turn / resume / sidebar-queue actions for the chat controller.
 */

import {
  useCallback,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import type { streamChatResume, streamChatTurn } from "../api";
import type { HistoryMessage } from "../contracts";
import {
  isSendDisabled,
  type ChatAction,
  type ChatState,
} from "../reducer";
import {
  createIdempotencyKey,
  enqueuePendingSidebarTurn,
  flushPendingSidebarHead,
  nowIso,
  type PendingSidebarTurn,
} from "./chatControllerSupport";
import type { useChatStream } from "./useChatStream";

type StreamTurn = typeof streamChatTurn;
type StreamResume = typeof streamChatResume;
type StreamApi = ReturnType<typeof useChatStream>;

export function useChatTurnActions(opts: {
  readonly dispatch: Dispatch<ChatAction>;
  readonly stateRef: MutableRefObject<ChatState>;
  readonly messagesRef: MutableRefObject<readonly HistoryMessage[]>;
  readonly hydratingRef: MutableRefObject<boolean>;
  readonly resumeModeRef: MutableRefObject<"approve" | "correct" | null>;
  readonly correctionModeRef: MutableRefObject<boolean>;
  readonly pendingSidebarQueueRef: MutableRefObject<PendingSidebarTurn[]>;
  readonly setDraft: (value: string) => void;
  readonly setResumeMode: (value: "approve" | "correct" | null) => void;
  readonly setCorrectionMode: (value: boolean) => void;
  readonly setPendingSidebarEpoch: Dispatch<SetStateAction<number>>;
  readonly streamTurn: StreamTurn;
  readonly streamResume: StreamResume;
  readonly runStream: StreamApi["runStream"];
  readonly streamHandlers: StreamApi["streamHandlers"];
  readonly abortActiveStream: StreamApi["abortActiveStream"];
  readonly activeRunId: string | null;
  readonly phase: ChatState["phase"];
  readonly resumeMode: "approve" | "correct" | null;
}) {
  const {
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
    activeRunId,
    phase,
    resumeMode,
  } = opts;

  const isTurnBlocked = useCallback(() => {
    return (
      hydratingRef.current ||
      isSendDisabled(stateRef.current) ||
      resumeModeRef.current !== null
    );
  }, [hydratingRef, resumeModeRef, stateRef]);

  const startTurn = useCallback(
    (text: string, attachmentIds?: readonly string[]) => {
      const trimmed = text.trim();
      if (!trimmed || isTurnBlocked()) {
        return false;
      }

      const userMessage: HistoryMessage = {
        role: "user",
        content: trimmed,
        created_at: nowIso(),
        structured_payload: null,
      };

      dispatch({
        type: "HYDRATE_HISTORY",
        messages: [...messagesRef.current, userMessage],
      });
      setDraft("");
      setCorrectionMode(false);

      const idempotencyKey = createIdempotencyKey();
      void runStream(
        async (signal) => {
          await streamTurn(
            {
              text: trimmed,
              idempotency_key: idempotencyKey,
              attachment_ids: attachmentIds ? [...attachmentIds] : undefined,
            },
            streamHandlers(),
            { signal },
          );
        },
        () => {
          setResumeMode(null);
        },
      );
      return true;
    },
    [
      dispatch,
      isTurnBlocked,
      messagesRef,
      runStream,
      setCorrectionMode,
      setDraft,
      setResumeMode,
      streamHandlers,
      streamTurn,
    ],
  );

  const handleResume = useCallback(
    (action: "approve" | "correct", correctionText?: string) => {
      if (!activeRunId || phase !== "awaiting_approval") {
        return false;
      }
      if (resumeMode !== null) {
        return false;
      }

      const trimmedCorrection =
        action === "correct" ? (correctionText ?? "").trim() : "";
      if (action === "correct" && trimmedCorrection.length === 0) {
        return false;
      }

      setResumeMode(action);
      setCorrectionMode(false);
      const runId = activeRunId;
      const idempotencyKey = createIdempotencyKey();

      void runStream(
        async (signal) => {
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
        },
        () => {
          setResumeMode(null);
        },
      );
      return true;
    },
    [
      activeRunId,
      phase,
      resumeMode,
      runStream,
      setCorrectionMode,
      setResumeMode,
      streamHandlers,
      streamResume,
    ],
  );

  const handleSubmit = useCallback(
    (value: string, attachmentIds?: readonly string[]): boolean => {
      if (
        correctionModeRef.current &&
        stateRef.current.phase === "awaiting_approval"
      ) {
        const trimmed = value.trim();
        if (!trimmed) {
          return false;
        }
        setDraft("");
        return handleResume("correct", trimmed);
      }
      return startTurn(value, attachmentIds);
    },
    [correctionModeRef, handleResume, setDraft, startTurn, stateRef],
  );

  const submitSidebarCvTurn = useCallback(
    (attachmentId: string, text: string) => {
      const trimmed = text.trim();
      const id = attachmentId.trim();
      if (!trimmed || !id) {
        return false;
      }
      if (!isTurnBlocked() && pendingSidebarQueueRef.current.length === 0) {
        return startTurn(trimmed, [id]);
      }
      enqueuePendingSidebarTurn(pendingSidebarQueueRef.current, {
        attachmentId: id,
        text: trimmed,
      });
      setPendingSidebarEpoch((n) => n + 1);
      return true;
    },
    [
      isTurnBlocked,
      pendingSidebarQueueRef,
      setPendingSidebarEpoch,
      startTurn,
    ],
  );

  const flushPendingSidebarQueue = useCallback(() => {
    if (isTurnBlocked()) {
      return;
    }
    flushPendingSidebarHead(pendingSidebarQueueRef.current, (turn) =>
      startTurn(turn.text, [turn.attachmentId]),
    );
  }, [isTurnBlocked, pendingSidebarQueueRef, startTurn]);

  const handleStop = useCallback(() => {
    abortActiveStream();
    dispatch({ type: "STREAM_ABORTED" });
  }, [abortActiveStream, dispatch]);

  return {
    startTurn,
    handleResume,
    handleSubmit,
    submitSidebarCvTurn,
    flushPendingSidebarQueue,
    handleStop,
  };
}

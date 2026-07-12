/**
 * Shared abortable stream runner + SSE event dispatch for chat turns/resumes.
 */

import { useCallback, useRef } from "react";

import type { ChatSSEEvent } from "../contracts";
import type { ChatAction } from "../reducer";

export function useChatStream(
  dispatch: (action: ChatAction) => void,
  onRunCompleted?: () => void,
) {
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const onRunCompletedRef = useRef(onRunCompleted);
  onRunCompletedRef.current = onRunCompleted;

  const markMounted = useCallback((mounted: boolean) => {
    mountedRef.current = mounted;
    if (!mounted) {
      abortRef.current?.abort();
    }
  }, []);

  const abortActiveStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const streamHandlers = useCallback(
    () => ({
      onEvent: (event: ChatSSEEvent) => {
        dispatch({ type: "SSE_EVENT", event });
        if (event.event === "run_completed") {
          onRunCompletedRef.current?.();
        }
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
    [dispatch],
  );

  const runStream = useCallback(
    async (
      start: (signal: AbortSignal) => Promise<void>,
      onFinally?: () => void,
    ) => {
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
          onFinally?.();
        }
      }
    },
    [abortActiveStream, dispatch],
  );

  return {
    markMounted,
    abortActiveStream,
    streamHandlers,
    runStream,
  };
}

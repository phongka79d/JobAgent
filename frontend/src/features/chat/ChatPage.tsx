/**
 * Base Astryx conversation page over the Plan 3 history/SSE API path.
 * Single owner of UI dispatch into the chatReducer — no second stream store.
 * Plan 4: PDF attachment token + profile_commit approval resume/focus.
 */

import {useCallback, useEffect, useReducer, useRef, useState} from 'react';
import {
  ChatComposer,
  ChatComposerDrawer,
  ChatComposerInput,
  ChatLayout,
  ChatSystemMessage,
  type ChatComposerInputHandle,
} from '@astryxdesign/core/Chat';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {FileInput} from '@astryxdesign/core/FileInput';
import {Token} from '@astryxdesign/core/Token';
import {VStack} from '@astryxdesign/core/VStack';

import {
  ChatApiError,
  fetchChatHistory,
  streamChatResume,
  streamChatTurn,
  streamCvReprocess,
  type StreamCallbacks,
} from '../../lib/api/chat';
import {uploadCv as defaultUploadCv} from '../profile/api';
import type {ProfileApprovalAction} from '../profile/ApprovalCard';
import type {PendingPdfAttachment} from '../profile/types';
import {ChatMessages} from './components/ChatMessages';
import {
  chatReducer,
  createInitialChatState,
  isComposerLocked,
} from './reducer';

export type ChatPageDeps = {
  loadHistory?: typeof fetchChatHistory;
  sendTurn?: typeof streamChatTurn;
  /** Injectable resume transport for approval actions. */
  resumeRun?: typeof streamChatResume;
  /** Injectable CV reprocess SSE transport (defaults to streamCvReprocess). */
  reprocessCv?: typeof streamCvReprocess;
  /** Shared CV upload used by composer attachment (same as sidebar). */
  uploadCv?: typeof defaultUploadCv;
};

/** One concise sidebar-driven turn: attachment ID only, no PDF body. */
export type SidebarAttachmentTurnRequest = {
  /** Monotonic key so the same id can re-fire after completion. */
  requestKey: number;
  attachmentId: string;
  message: string;
};

/** CV Manager reprocess request composed through App (same SSE owner as turns). */
export type CvReprocessRequest = {
  requestKey: number;
  attachmentId: string;
  message: string;
};

export type CvReprocessTerminal =
  | 'completed'
  | 'failed'
  | 'interrupted'
  | 'http_error';

export type ChatPageProps = {
  /** Injectable transport for tests; defaults to Plan 3/4 API clients. */
  deps?: ChatPageDeps;
  /** Reflect lock to App/sidebar so upload disables with composer. */
  onInteractionLockChange?: (locked: boolean) => void;
  /** Sidebar successful upload → start one normal turn with attachment_id. */
  sidebarAttachmentTurn?: SidebarAttachmentTurnRequest | null;
  onSidebarAttachmentTurnHandled?: (requestKey: number) => void;
  /** CV Manager reprocess → sole streamCvReprocess + chatReducer path. */
  cvReprocessRequest?: CvReprocessRequest | null;
  onCvReprocessHandled?: (requestKey: number) => void;
  /** Notify sidebar when reprocess stream ends (clear pending / surface error). */
  onCvReprocessTerminal?: (
    requestKey: number,
    attachmentId: string,
    kind: CvReprocessTerminal,
    error?: {code: string; summary: string},
  ) => void;
  /** After save_profile completes successfully — refresh approved sidebar. */
  onProfileSaved?: () => void;
};

function newClientKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const MAX_PDF_BYTES = 10 * 1024 * 1024;

export function ChatPage({
  deps,
  onInteractionLockChange,
  sidebarAttachmentTurn,
  onSidebarAttachmentTurnHandled,
  cvReprocessRequest,
  onCvReprocessHandled,
  onCvReprocessTerminal,
  onProfileSaved,
}: ChatPageProps) {
  const loadHistory = deps?.loadHistory ?? fetchChatHistory;
  const sendTurn = deps?.sendTurn ?? streamChatTurn;
  const resumeRun = deps?.resumeRun ?? streamChatResume;
  const reprocessCv = deps?.reprocessCv ?? streamCvReprocess;
  const doUpload = deps?.uploadCv ?? defaultUploadCv;

  const [state, dispatch] = useReducer(
    chatReducer,
    undefined,
    createInitialChatState,
  );
  const [historyLoadError, setHistoryLoadError] = useState<string | null>(null);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const [draft, setDraft] = useState('');
  const [pendingPdf, setPendingPdf] = useState<PendingPdfAttachment | null>(
    null,
  );
  const [composerFile, setComposerFile] = useState<File | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [isAttaching, setIsAttaching] = useState(false);
  /** Local only: first accepted approval action per run (not a second store). */
  const [approvalLockedRunIds, setApprovalLockedRunIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const abortRef = useRef<AbortController | null>(null);
  /** Set true synchronously when a turn/resume starts; cleared on terminal UI phases. */
  const inFlightRef = useRef(false);
  const handledSidebarKeysRef = useRef<Set<number>>(new Set());
  const handledReprocessKeysRef = useRef<Set<number>>(new Set());
  /** Guards rapid double-clicks before React re-renders disabled buttons. */
  const approvalInFlightRef = useRef<Set<string>>(new Set());
  const composerInputRef = useRef<ChatComposerInputHandle | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const onProfileSavedRef = useRef(onProfileSaved);
  onProfileSavedRef.current = onProfileSaved;
  const onCvReprocessTerminalRef = useRef(onCvReprocessTerminal);
  onCvReprocessTerminalRef.current = onCvReprocessTerminal;

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

  const locked = isComposerLocked(state);
  useEffect(() => {
    onInteractionLockChange?.(locked);
  }, [locked, onInteractionLockChange]);

  // Initial history hydration (newest page) — reconstructs pending approval cards.
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

  /**
   * After a terminal turn, re-fetch durable history so ToolResult.data
   * (including compact save_job cards) replaces stream-null resultData.
   * Live and restart paths share history/rehydrate — no second store.
   */
  const rehydrateDurableHistory = useCallback(async () => {
    try {
      const page = await loadHistory({limit: 50});
      dispatch({type: 'history/rehydrate', page});
    } catch {
      // Leave stream/reducer state; do not invent tool results.
    }
  }, [loadHistory]);

  const makeStreamCallbacks = useCallback(
    (opts?: {
      onTerminal?: (kind: 'completed' | 'failed' | 'interrupted') => void;
    }): StreamCallbacks => {
      return {
        onEvent: (event) => {
          dispatch({type: 'sse/event', event});
          if (event.event === 'run_completed') {
            inFlightRef.current = false;
            opts?.onTerminal?.('completed');
            void rehydrateDurableHistory();
          } else if (event.event === 'run_failed') {
            inFlightRef.current = false;
            opts?.onTerminal?.('failed');
            void rehydrateDurableHistory();
          } else if (event.event === 'approval_required') {
            inFlightRef.current = false;
            opts?.onTerminal?.('interrupted');
          }
        },
        onMalformed: () => {
          // Malformed frames must not invent completion (reducer ignores via sse/raw).
        },
        onDisconnected: () => {
          if (inFlightRef.current) {
            inFlightRef.current = false;
            dispatch({type: 'stream/disconnected'});
          }
        },
      };
    },
    [rehydrateDurableHistory],
  );

  const runTurn = useCallback(
    (message: string, attachmentIds: string[]) => {
      const trimmed = message.trim();
      // Allow ID-only turns when message is the concise sidebar intent;
      // still require non-empty message (backend contract).
      if (trimmed === '' || isComposerLocked(stateRef.current)) {
        return false;
      }

      setDraft('');
      setPendingPdf(null);
      setComposerFile(null);
      setAttachError(null);
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const clientKey = newClientKey('user');
      inFlightRef.current = true;
      dispatch({type: 'turn/start', clientKey, message: trimmed});

      const callbacks = makeStreamCallbacks();

      void (async () => {
        try {
          await sendTurn(
            {
              message: trimmed,
              attachment_ids: attachmentIds,
            },
            callbacks,
            controller.signal,
          );
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
      return true;
    },
    [makeStreamCallbacks, sendTurn],
  );

  const handleSubmit = useCallback(
    (value: string) => {
      const ids = pendingPdf ? [pendingPdf.attachmentId] : [];
      runTurn(value, ids);
    },
    [pendingPdf, runTurn],
  );

  const focusComposer = useCallback(() => {
    // Documented ChatComposerInput focus handle (public Astryx API).
    const focus = () => {
      composerInputRef.current?.focus();
    };
    // Defer until after unlock re-render enables the contenteditable.
    if (typeof queueMicrotask === 'function') {
      queueMicrotask(() => {
        requestAnimationFrame(focus);
      });
    } else {
      setTimeout(focus, 0);
    }
  }, []);

  /** Focus the existing approval card after reprocess reaches approval_required. */
  const focusApprovalCard = useCallback(() => {
    const focus = () => {
      const card = document.querySelector(
        '[data-testid="jobagent-approval-card"]',
      );
      if (card instanceof HTMLElement) {
        card.scrollIntoView({block: 'nearest', behavior: 'smooth'});
        const action = card.querySelector(
          '[data-testid="jobagent-approval-save"]',
        );
        if (action instanceof HTMLElement) {
          action.focus();
        } else {
          card.focus();
        }
      }
    };
    if (typeof queueMicrotask === 'function') {
      queueMicrotask(() => {
        requestAnimationFrame(focus);
      });
    } else {
      setTimeout(focus, 0);
    }
  }, []);

  const handleApprovalAction = useCallback(
    (runId: string, action: ProfileApprovalAction) => {
      // One accepted action per run: ignore rapid repeats and second store.
      if (
        approvalInFlightRef.current.has(runId) ||
        approvalLockedRunIds.has(runId)
      ) {
        return;
      }
      approvalInFlightRef.current.add(runId);
      setApprovalLockedRunIds((prev) => {
        const next = new Set(prev);
        next.add(runId);
        return next;
      });

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      inFlightRef.current = true;

      const callbacks = makeStreamCallbacks({
        onTerminal: (kind) => {
          approvalInFlightRef.current.delete(runId);
          if (kind === 'completed') {
            if (action === 'save_profile') {
              onProfileSavedRef.current?.();
            } else if (action === 'request_changes') {
              focusComposer();
            }
          }
        },
      });

      void (async () => {
        try {
          await resumeRun(runId, action, callbacks, controller.signal);
        } catch (err) {
          if (controller.signal.aborted) {
            return;
          }
          approvalInFlightRef.current.delete(runId);
          // Keep buttons locked after an accepted action; surface failure truthfully.
          // Terminal no-op or HTTP errors never invent success.
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
              err instanceof Error ? err.message : 'Resume failed unexpectedly',
          });
        }
      })();
    },
    [approvalLockedRunIds, focusComposer, makeStreamCallbacks, resumeRun],
  );

  // Sidebar upload success → one normal concise turn with attachment_id only.
  useEffect(() => {
    if (!sidebarAttachmentTurn) {
      return;
    }
    const {requestKey, attachmentId, message} = sidebarAttachmentTurn;
    if (handledSidebarKeysRef.current.has(requestKey)) {
      return;
    }
    if (isComposerLocked(stateRef.current)) {
      // Wait until unlock; do not mark handled so it can retry.
      return;
    }
    handledSidebarKeysRef.current.add(requestKey);
    const started = runTurn(message, [attachmentId]);
    if (started) {
      onSidebarAttachmentTurnHandled?.(requestKey);
    } else {
      handledSidebarKeysRef.current.delete(requestKey);
    }
  }, [
    sidebarAttachmentTurn,
    runTurn,
    onSidebarAttachmentTurnHandled,
    state.streamPhase,
    state.pendingApproval,
    state.messages,
  ]);

  // CV Manager reprocess → streamCvReprocess into the same reducer; focus approval.
  useEffect(() => {
    if (!cvReprocessRequest) {
      return;
    }
    const {requestKey, attachmentId, message} = cvReprocessRequest;
    if (handledReprocessKeysRef.current.has(requestKey)) {
      return;
    }
    if (isComposerLocked(stateRef.current) || inFlightRef.current) {
      return;
    }
    handledReprocessKeysRef.current.add(requestKey);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const clientKey = newClientKey('user');
    inFlightRef.current = true;
    dispatch({type: 'turn/start', clientKey, message});

    const callbacks = makeStreamCallbacks({
      onTerminal: (kind) => {
        onCvReprocessTerminalRef.current?.(requestKey, attachmentId, kind);
        if (kind === 'interrupted') {
          focusApprovalCard();
        }
      },
    });

    // Focus approval as soon as the interrupt event lands (before terminal settle).
    const wrapped: StreamCallbacks = {
      onEvent: (event) => {
        callbacks.onEvent(event);
        if (event.event === 'approval_required') {
          focusApprovalCard();
        }
      },
      onMalformed: callbacks.onMalformed,
      onDisconnected: callbacks.onDisconnected,
    };

    void (async () => {
      try {
        await reprocessCv(attachmentId, wrapped, controller.signal);
        onCvReprocessHandled?.(requestKey);
      } catch (err) {
        if (controller.signal.aborted) {
          onCvReprocessHandled?.(requestKey);
          return;
        }
        inFlightRef.current = false;
        if (err instanceof ChatApiError) {
          dispatch({
            type: 'stream/http_failed',
            code: err.code,
            summary: err.summary,
          });
          onCvReprocessTerminalRef.current?.(
            requestKey,
            attachmentId,
            'http_error',
            {code: err.code, summary: err.summary},
          );
        } else {
          const summary =
            err instanceof Error ? err.message : 'Reprocess failed unexpectedly';
          dispatch({
            type: 'stream/http_failed',
            code: 'STREAM_ERROR',
            summary,
          });
          onCvReprocessTerminalRef.current?.(
            requestKey,
            attachmentId,
            'http_error',
            {code: 'STREAM_ERROR', summary},
          );
        }
        onCvReprocessHandled?.(requestKey);
      }
    })();
  }, [
    cvReprocessRequest,
    focusApprovalCard,
    makeStreamCallbacks,
    onCvReprocessHandled,
    reprocessCv,
    state.streamPhase,
    state.pendingApproval,
    state.messages,
  ]);

  const handleComposerFileChange = useCallback(
    (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      setComposerFile(file);
      setAttachError(null);
    },
    [],
  );

  const handleComposerAttach = useCallback(
    async (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      if (!file || locked || isAttaching) {
        return;
      }
      setIsAttaching(true);
      setAttachError(null);
      try {
        const result = await doUpload(file);
        // Compact PDF token: display name + ID only (no bytes/path).
        setPendingPdf({
          attachmentId: result.attachment.id,
          displayName: result.attachment.original_name,
        });
        setComposerFile(null);
      } catch (err) {
        const code = err instanceof ChatApiError ? err.code : 'UPLOAD_FAILED';
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'CV attach failed';
        setAttachError(`${summary} (${code})`);
        setPendingPdf(null);
      } finally {
        setIsAttaching(false);
      }
    },
    [doUpload, isAttaching, locked],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const isStreaming =
    state.streamPhase === 'streaming' || state.streamPhase === 'connecting';
  const hasInterrupted = state.messages.some(
    (m) => m.run?.state === 'interrupted',
  ) || state.pendingApproval !== null;

  const composerStatus =
    attachError
      ? {
          type: 'error' as const,
          message: attachError,
        }
      : state.streamPhase === 'failed' && state.streamError
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
                message:
                  'Run interrupted — new turns are blocked until resumed',
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

  const scrollToTopAction =
    state.nextCursor !== null && !isLoadingOlder
      ? async () => {
          await handleLoadOlder();
        }
      : undefined;

  const uploadDisabled = locked || isAttaching;

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
            input={
              <ChatComposerInput
                handleRef={composerInputRef}
                data-testid="jobagent-chat-composer-input"
              />
            }
            headerActions={
              <FileInput
                label="Attach PDF"
                value={composerFile}
                onChange={handleComposerFileChange}
                changeAction={handleComposerAttach}
                accept="application/pdf,.pdf"
                maxSize={MAX_PDF_BYTES}
                mode="input"
                isLabelHidden
                isDisabled={uploadDisabled}
                disabledMessage={
                  locked
                    ? 'Attachment upload is disabled while a run is active or interrupted'
                    : undefined
                }
                isLoading={isAttaching}
                placeholder="PDF"
                data-testid="jobagent-chat-pdf-upload"
              />
            }
            drawer={
              pendingPdf ? (
                <ChatComposerDrawer
                  count={1}
                  label="Attachments"
                  data-testid="jobagent-chat-pdf-drawer"
                >
                  <Token
                    label={pendingPdf.displayName}
                    description={`PDF attachment ${pendingPdf.attachmentId}`}
                    onRemove={
                      locked
                        ? undefined
                        : () => {
                            setPendingPdf(null);
                          }
                    }
                    data-testid="jobagent-chat-pdf-token"
                  />
                </ChatComposerDrawer>
              ) : undefined
            }
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
            onApprovalAction={handleApprovalAction}
            approvalLockedRunIds={approvalLockedRunIds}
          />
        ) : null}
      </ChatLayout>
    </VStack>
  );
}

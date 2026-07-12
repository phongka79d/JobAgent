/**
 * Small pure helpers for the chat transport controller (ids + composer status).
 */

import type { ChatState } from "../reducer";

export function createIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}

export type ComposerStatus =
  | { type: "error" | "warning"; message?: string }
  | undefined;

export function resolveComposerStatus(
  state: ChatState,
  hydrateError: string | null,
): ComposerStatus {
  if (state.phase === "failed" && state.failure) {
    return {
      type: "error",
      message:
        state.failure.message?.trim() ||
        `Run failed (${state.failure.errorCode})`,
    };
  }
  if (state.phase === "disconnected") {
    return {
      type: "warning",
      message: "Connection interrupted. Send again when ready.",
    };
  }
  if (hydrateError) {
    return {
      type: "error",
      message: "Could not load conversation history.",
    };
  }
  return undefined;
}

/** Composer disable + approval disable flags for approval/correction UX. */
export function resolveInteractionFlags(args: {
  readonly phase: ChatState["phase"];
  readonly hydrating: boolean;
  readonly resumeMode: "approve" | "correct" | null;
  readonly correctionMode: boolean;
  readonly sendBlockedByPhase: boolean;
}): {
  readonly sendDisabled: boolean;
  readonly approvalDisabled: boolean;
  readonly composerPlaceholder: string;
} {
  const sendDisabled =
    args.resumeMode !== null ||
    args.hydrating ||
    (args.correctionMode ? false : args.sendBlockedByPhase);
  const approvalDisabled =
    args.resumeMode !== null ||
    args.phase !== "awaiting_approval" ||
    args.correctionMode;
  return {
    sendDisabled,
    approvalDisabled,
    composerPlaceholder: args.correctionMode
      ? "Describe the profile changes…"
      : "Message JobAgent…",
  };
}

/** Deferred sidebar CV turn while hydrate/send is temporarily blocked. */
export interface PendingSidebarTurn {
  readonly attachmentId: string;
  readonly text: string;
}

/** Append to a FIFO of deferred sidebar turns (no overwrite of prior items). */
export function enqueuePendingSidebarTurn(
  queue: PendingSidebarTurn[],
  turn: PendingSidebarTurn,
): void {
  queue.push(turn);
}

/**
 * Pop the FIFO head and start it. Restores head if `start` returns false.
 * Returns whether a start was attempted.
 */
export function flushPendingSidebarHead(
  queue: PendingSidebarTurn[],
  start: (turn: PendingSidebarTurn) => boolean,
): boolean {
  const next = queue.shift();
  if (!next) {
    return false;
  }
  if (!start(next)) {
    queue.unshift(next);
  }
  return true;
}

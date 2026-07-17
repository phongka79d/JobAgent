/**
 * CV Manager sidebar-local action slice (Plan 9 / Master §15.6).
 * Pending/error maps and pure selection helpers only.
 * Full observability reducer ownership stays in state.ts.
 */

import type {CvManagerActionKind} from './cvManagerTypes';
import {selectSafeRemainingAttachmentId} from './cvManagerTypes';
import type {ObservabilitySafeError} from './types';

export type {CvManagerActionKind};
export {selectSafeRemainingAttachmentId};

export type CvManagerActionSlice = {
  /** attachmentId → in-flight action kind (at most one per attachment). */
  pendingByAttachment: Readonly<Record<string, CvManagerActionKind>>;
  /** attachmentId → last safe action error (cleared on next success start). */
  errorsByAttachment: Readonly<Record<string, ObservabilitySafeError>>;
};

export const initialCvManagerActionSlice: CvManagerActionSlice = {
  pendingByAttachment: {},
  errorsByAttachment: {},
};

export type CvManagerDispatchAction =
  | {
      type: 'cv_action_begin';
      attachmentId: string;
      kind: CvManagerActionKind;
    }
  | {
      type: 'cv_action_end';
      attachmentId: string;
    }
  | {
      type: 'cv_action_error';
      attachmentId: string;
      error: ObservabilitySafeError;
    }
  | {
      type: 'cv_delete_success';
      attachmentId: string;
      remainingItems: ReadonlyArray<{id: string; state: string}>;
    }
  | {
      type: 'cv_invalidate_activation';
    }
  | {
      type: 'cv_clear_action_error';
      attachmentId: string;
    };

/** True when any action is in flight for the attachment (blocks duplicates). */
export function isCvActionPending(
  slice: CvManagerActionSlice,
  attachmentId: string,
): boolean {
  return slice.pendingByAttachment[attachmentId] !== undefined;
}

/** True when this attachment already has the same kind pending. */
export function isCvActionKindPending(
  slice: CvManagerActionSlice,
  attachmentId: string,
  kind: CvManagerActionKind,
): boolean {
  return slice.pendingByAttachment[attachmentId] === kind;
}

export function dropPendingAttachment(
  pending: Readonly<Record<string, CvManagerActionKind>>,
  attachmentId: string,
): Record<string, CvManagerActionKind> {
  if (!(attachmentId in pending)) {
    return pending as Record<string, CvManagerActionKind>;
  }
  const next = {...pending};
  delete next[attachmentId];
  return next;
}

export function dropActionError(
  errors: Readonly<Record<string, ObservabilitySafeError>>,
  attachmentId: string,
): Record<string, ObservabilitySafeError> {
  if (!(attachmentId in errors)) {
    return errors as Record<string, ObservabilitySafeError>;
  }
  const next = {...errors};
  delete next[attachmentId];
  return next;
}

/**
 * Local zero-result recovery action state (Plan 10 / Batch07).
 * Separate from chatReducer/SSE truth: pending, unavailable, error, and
 * persisted MatchCard payload only. Submits durable source_message_id via
 * accepted jobs client; never reads composer/latest message text.
 */

import {useCallback, useRef, useState} from 'react';

import {
  saveAndEvaluateJob as defaultSaveAndEvaluateJob,
  toSavedJobActionError,
} from '../jobs/api';
import type {CompactMatchResult} from '../jobs/matchResult';
import type {SaveAndEvaluateResponse} from '../jobs/types';
import {
  EMPTY_MATCH_ERROR_HINT,
  EMPTY_MATCH_UNAVAILABLE_HINT,
} from './components/EmptyMatchResultCard';

export type RecoveryPhase =
  | 'idle'
  | 'pending'
  | 'success'
  | 'unavailable'
  | 'error';

export type RecoveryEntry = {
  phase: RecoveryPhase;
  recoveredMatch: CompactMatchResult | null;
  failureHint: string | null;
};

export type SavedJobRecoveryApi = {
  saveAndEvaluateJob: (
    sourceMessageId: string,
    signal?: AbortSignal,
  ) => Promise<SaveAndEvaluateResponse>;
};

export type UseSavedJobRecoveryOptions = {
  api?: Partial<SavedJobRecoveryApi>;
  /** Called after created/reused/unavailable so saved-JD caches can refresh. */
  onInvalidated?: () => void;
};

const IDLE_ENTRY: RecoveryEntry = {
  phase: 'idle',
  recoveredMatch: null,
  failureHint: null,
};

export type RecoverOutcome = 'success' | 'unavailable' | 'duplicate' | 'error';

export function useSavedJobRecovery(
  options: UseSavedJobRecoveryOptions = {},
) {
  const saveAndEvaluate =
    options.api?.saveAndEvaluateJob ?? defaultSaveAndEvaluateJob;
  const onInvalidatedRef = useRef(options.onInvalidated);
  onInvalidatedRef.current = options.onInvalidated;

  const [byMessage, setByMessage] = useState<
    Readonly<Record<string, RecoveryEntry>>
  >({});
  /** Synchronous pending guard so rapid double-clicks cannot race re-render. */
  const inFlightRef = useRef<Set<string>>(new Set());

  const getEntry = useCallback(
    (sourceMessageId: string): RecoveryEntry =>
      byMessage[sourceMessageId] ?? IDLE_ENTRY,
    [byMessage],
  );

  const isPending = useCallback(
    (sourceMessageId: string): boolean =>
      inFlightRef.current.has(sourceMessageId) ||
      byMessage[sourceMessageId]?.phase === 'pending',
    [byMessage],
  );

  const recover = useCallback(
    async (
      sourceMessageId: string,
      opts?: {signal?: AbortSignal},
    ): Promise<RecoverOutcome> => {
      const id = sourceMessageId.trim();
      if (id === '') {
        return 'error';
      }
      if (inFlightRef.current.has(id)) {
        return 'duplicate';
      }
      inFlightRef.current.add(id);
      setByMessage((prev) => ({
        ...prev,
        [id]: {
          phase: 'pending',
          recoveredMatch: null,
          failureHint: null,
        },
      }));

      try {
        const response = await saveAndEvaluate(id, opts?.signal);
        if (opts?.signal?.aborted) {
          inFlightRef.current.delete(id);
          setByMessage((prev) => ({
            ...prev,
            [id]: IDLE_ENTRY,
          }));
          return 'error';
        }
        inFlightRef.current.delete(id);

        if (
          (response.evaluation_outcome === 'created' ||
            response.evaluation_outcome === 'reused') &&
          response.evaluation
        ) {
          setByMessage((prev) => ({
            ...prev,
            [id]: {
              phase: 'success',
              recoveredMatch: response.evaluation!.result,
              failureHint: null,
            },
          }));
          onInvalidatedRef.current?.();
          return 'success';
        }

        // unavailable (or missing evaluation): keep card, no success claim.
        setByMessage((prev) => ({
          ...prev,
          [id]: {
            phase: 'unavailable',
            recoveredMatch: null,
            failureHint: EMPTY_MATCH_UNAVAILABLE_HINT,
          },
        }));
        // Job may still have been ingested — refresh list/detail projections.
        onInvalidatedRef.current?.();
        return 'unavailable';
      } catch (err) {
        inFlightRef.current.delete(id);
        if (opts?.signal?.aborted) {
          setByMessage((prev) => ({
            ...prev,
            [id]: IDLE_ENTRY,
          }));
          return 'error';
        }
        const safe = toSavedJobActionError(err);
        setByMessage((prev) => ({
          ...prev,
          [id]: {
            phase: 'error',
            recoveredMatch: null,
            failureHint: safe.summary || EMPTY_MATCH_ERROR_HINT,
          },
        }));
        return 'error';
      }
    },
    [saveAndEvaluate],
  );

  return {
    getEntry,
    isPending,
    recover,
  };
}

import {useCallback, useEffect, useRef, useState} from 'react';

import {defaultCvManagerApi, type CvManagerApi} from './api';
import type {CvManagerItem, ProfileReextractReview, ProfileReextractStage} from './types';

export type CvManagerSafeError = {code: string; summary: string};
type ProfileReextractState = {
  phase: 'idle' | 'loading' | 'review' | 'error';
  profileId: string | null;
  stage: ProfileReextractStage | null;
  review: ProfileReextractReview | null;
  error: CvManagerSafeError | null;
  /** A durable draft means review actions, not a speculative retry, are allowed. */
  draftAvailable: boolean;
};
export type CvManagerViewState = {
  phase: 'closed' | 'loading' | 'ready' | 'error';
  items: CvManagerItem[];
  selectedId: string | null;
  pendingByAttachment: Record<string, true>;
  errorsByAttachment: Record<string, CvManagerSafeError>;
  deleteTargetId: string | null;
  reextract?: ProfileReextractState;
};

const EMPTY_REEXTRACT: ProfileReextractState = {phase: 'idle', profileId: null, stage: null, review: null, error: null, draftAvailable: false};

const CLOSED: CvManagerViewState = {
  phase: 'closed', items: [], selectedId: null, pendingByAttachment: {}, errorsByAttachment: {}, deleteTargetId: null,
  reextract: EMPTY_REEXTRACT,
};

function safeError(error: unknown): CvManagerSafeError {
  if (typeof error === 'object' && error !== null && 'code' in error && 'summary' in error && typeof error.code === 'string' && typeof error.summary === 'string') {
    return {code: error.code, summary: error.summary};
  }
  return {code: 'CV_MANAGER_REQUEST_FAILED', summary: 'Unable to refresh CVs. Try again.'};
}

export type UseCvManagerStateOptions = {
  api?: Partial<CvManagerApi>;
  profileId?: string | null;
  profileReady?: boolean;
};

export function useCvManagerState(options: UseCvManagerStateOptions = {}) {
  const api = {...defaultCvManagerApi, ...options.api} as Required<CvManagerApi>;
  const profileScope = options.profileId ?? 'legacy';
  const scopeRef = useRef(profileScope);
  const listControllerRef = useRef<AbortController | null>(null);
  const mutationControllersRef = useRef(new Map<string, AbortController>());
  const mutationInFlightRef = useRef(new Set<string>());
  const generationRef = useRef(0);
  const reextractGenerationRef = useRef(0);
  const stateRef = useRef<CvManagerViewState>(CLOSED);
  const [state, setState] = useState<CvManagerViewState>(CLOSED);

  const publish = useCallback((next: CvManagerViewState | ((previous: CvManagerViewState) => CvManagerViewState)) => {
    setState((previous) => {
      const resolved = typeof next === 'function' ? next(previous) : next;
      stateRef.current = resolved;
      return resolved;
    });
  }, []);

  useEffect(() => {
    if (scopeRef.current === profileScope) return;
    scopeRef.current = profileScope;
    generationRef.current += 1;
    listControllerRef.current?.abort();
    listControllerRef.current = null;
    for (const controller of mutationControllersRef.current.values()) controller.abort();
    mutationControllersRef.current.clear();
    mutationInFlightRef.current.clear();
    reextractGenerationRef.current += 1;
    publish(CLOSED);
  }, [profileScope, publish]);

  useEffect(() => () => {
    listControllerRef.current?.abort();
    for (const controller of mutationControllersRef.current.values()) controller.abort();
  }, []);

  const refresh = useCallback(async () => {
    const scope = scopeRef.current;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    listControllerRef.current?.abort();
    const controller = new AbortController();
    listControllerRef.current = controller;
    publish((previous) => ({...previous, phase: 'loading'}));
    try {
      const response = await api.fetchCvManager(controller.signal);
      if (controller.signal.aborted || scopeRef.current !== scope || generationRef.current !== generation) return false;
      publish((previous) => ({
        ...previous, phase: 'ready', items: response.items,
        selectedId: response.items.some((item) => item.id === previous.selectedId) ? previous.selectedId : (response.items[0]?.id ?? null),
      }));
      return true;
    } catch (error) {
      if (controller.signal.aborted || scopeRef.current !== scope || generationRef.current !== generation) return false;
      const errorId = '__list__';
      publish((previous) => ({...previous, phase: 'error', errorsByAttachment: {...previous.errorsByAttachment, [errorId]: safeError(error)}}));
      return false;
    }
  }, [api, publish]);

  const open = useCallback(async () => refresh(), [refresh]);
  const close = useCallback(() => {
    generationRef.current += 1;
    listControllerRef.current?.abort();
    listControllerRef.current = null;
    reextractGenerationRef.current += 1;
    mutationControllersRef.current.get('reextract')?.abort();
    publish((previous) => ({...previous, phase: 'closed', deleteTargetId: null}));
  }, [publish]);
  const select = useCallback((id: string | null) => {
    publish((previous) => ({...previous, selectedId: id}));
  }, [publish]);
  const openDeleteDialog = useCallback((id: string) => {
    const item = stateRef.current.items.find((candidate) => candidate.id === id);
    if (item?.allowed_actions.includes('delete_cv')) publish((previous) => ({...previous, deleteTargetId: id}));
  }, [publish]);
  const closeDeleteDialog = useCallback(() => publish((previous) => ({...previous, deleteTargetId: null})), [publish]);

  const confirmDelete = useCallback(async (id: string): Promise<boolean> => {
    const item = stateRef.current.items.find((candidate) => candidate.id === id);
    if (!item?.allowed_actions.includes('delete_cv') || mutationInFlightRef.current.has(id)) return false;
    mutationInFlightRef.current.add(id);
    const scope = scopeRef.current;
    const generation = generationRef.current;
    const controller = new AbortController();
    mutationControllersRef.current.set(id, controller);
    publish((previous) => ({...previous, pendingByAttachment: {...previous.pendingByAttachment, [id]: true}, errorsByAttachment: Object.fromEntries(Object.entries(previous.errorsByAttachment).filter(([key]) => key !== id)), deleteTargetId: null}));
    try {
      await api.deleteCv(id, controller.signal);
      if (controller.signal.aborted || scopeRef.current !== scope || generationRef.current !== generation) return false;
      mutationInFlightRef.current.delete(id);
      mutationControllersRef.current.delete(id);
      publish((previous) => {
        const pending = {...previous.pendingByAttachment};
        delete pending[id];
        return {...previous, pendingByAttachment: pending};
      });
      await refresh();
      return true;
    } catch (error) {
      if (controller.signal.aborted || scopeRef.current !== scope || generationRef.current !== generation) return false;
      mutationInFlightRef.current.delete(id);
      mutationControllersRef.current.delete(id);
      publish((previous) => {
        const pending = {...previous.pendingByAttachment};
        delete pending[id];
        return {...previous, phase: 'error', pendingByAttachment: pending, errorsByAttachment: {...previous.errorsByAttachment, [id]: safeError(error)}};
      });
      return false;
    } finally {
      mutationInFlightRef.current.delete(id);
      mutationControllersRef.current.delete(id);
    }
  }, [api, publish, refresh]);

  const loadReview = useCallback(async (profileId: string, expectedRevision?: string, signal?: AbortSignal, serverError: CvManagerSafeError | null = null): Promise<boolean> => {
    const scope = scopeRef.current;
    const reextractGeneration = reextractGenerationRef.current;
    try {
      const review = await api.getProfileReextractReview(profileId, signal);
      if (signal?.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== reextractGeneration) return false;
      if (review.profile_id !== profileId || (expectedRevision !== undefined && review.revision !== expectedRevision)) {
        publish((previous) => ({...previous, reextract: {phase: 'error', profileId, stage: null, review: null, error: {code: 'PROFILE_REEXTRACT_REVIEW_MISMATCH', summary: 'The review changed; reload it before continuing.'}, draftAvailable: false}}));
        return false;
      }
      publish((previous) => ({...previous, reextract: {phase: 'review', profileId, stage: null, review, error: serverError, draftAvailable: true}}));
      return true;
    } catch (error) {
      if (signal?.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== reextractGeneration) return false;
      publish((previous) => ({...previous, reextract: {...(previous.reextract ?? EMPTY_REEXTRACT), phase: 'error', profileId, review: null, error: safeError(error), draftAvailable: serverError !== null}}));
      return false;
    }
  }, [api, publish]);

  const startReextract = useCallback(async (profileId: string): Promise<boolean> => {
    const key = 'reextract';
    mutationControllersRef.current.get(key)?.abort();
    const controller = new AbortController();
    mutationControllersRef.current.set(key, controller);
    const scope = scopeRef.current;
    const reextractGeneration = reextractGenerationRef.current + 1;
    reextractGenerationRef.current = reextractGeneration;
    publish((previous) => ({...previous, reextract: {phase: 'loading', profileId, stage: 'validating_source', review: null, error: null, draftAvailable: false}}));
    let reviewRevision: string | null = null;
    let failure: {error: CvManagerSafeError; draftAvailable: boolean} | null = null;
    try {
      await api.streamProfileReextract(profileId, {
        onEvent: (event) => {
          if (controller.signal.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== reextractGeneration || event.profile_id !== profileId) return;
          if (event.event === 'reextract_progress') {
            publish((previous) => ({...previous, reextract: {...(previous.reextract ?? EMPTY_REEXTRACT), phase: 'loading', profileId, stage: event.payload.stage, error: null, draftAvailable: false}}));
          } else if (event.event === 'reextract_review_ready') {
            reviewRevision = event.payload.revision;
          } else {
            failure = {error: {code: event.payload.code, summary: event.payload.summary}, draftAvailable: event.payload.draft_available};
          }
        },
        onMalformed: () => undefined,
        onDisconnected: () => undefined,
      }, controller.signal);
      if (controller.signal.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== reextractGeneration) return false;
      if (failure !== null) {
        if (failure.draftAvailable) {
          return await loadReview(profileId, undefined, controller.signal, failure.error);
        }
        publish((previous) => ({...previous, reextract: {phase: 'error', profileId, stage: null, review: null, error: failure.error, draftAvailable: false}}));
        return false;
      }
      return await loadReview(profileId, reviewRevision ?? undefined, controller.signal);
    } catch (error) {
      if (controller.signal.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== reextractGeneration) return false;
      if (await loadReview(profileId, undefined, controller.signal)) return true;
      publish((previous) => ({...previous, reextract: {...(previous.reextract ?? EMPTY_REEXTRACT), phase: 'error', profileId, review: null, error: safeError(error), draftAvailable: false}}));
      return false;
    } finally {
      mutationControllersRef.current.delete(key);
    }
  }, [api, loadReview, publish]);

  const approveReview = useCallback(async (): Promise<boolean> => {
    const review = stateRef.current.reextract?.review;
    if (!review?.can_approve) return false;
    const scope = scopeRef.current;
    const generation = reextractGenerationRef.current;
    const controller = new AbortController();
    try {
      await api.approveProfileReextractReview(review.profile_id, review.revision, controller.signal);
      if (controller.signal.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== generation) return false;
      publish((previous) => ({...previous, reextract: EMPTY_REEXTRACT}));
      await refresh();
      return true;
    } catch (error) {
      if (scopeRef.current !== scope || reextractGenerationRef.current !== generation) return false;
      publish((previous) => ({...previous, reextract: {...(previous.reextract ?? EMPTY_REEXTRACT), phase: 'error', error: safeError(error)}}));
      return false;
    }
  }, [api, publish, refresh]);

  const discardReview = useCallback(async (): Promise<boolean> => {
    const review = stateRef.current.reextract?.review;
    if (!review?.can_discard) return false;
    const scope = scopeRef.current;
    const generation = reextractGenerationRef.current;
    const controller = new AbortController();
    try {
      await api.discardProfileReextractReview(review.profile_id, review.revision, controller.signal);
      if (controller.signal.aborted || scopeRef.current !== scope || reextractGenerationRef.current !== generation) return false;
      publish((previous) => ({...previous, reextract: EMPTY_REEXTRACT}));
      return true;
    } catch (error) {
      if (scopeRef.current !== scope || reextractGenerationRef.current !== generation) return false;
      publish((previous) => ({...previous, reextract: {...(previous.reextract ?? EMPTY_REEXTRACT), phase: 'error', error: safeError(error)}}));
      return false;
    }
  }, [api, publish]);

  const closeReview = useCallback(() => publish((previous) => ({...previous, reextract: EMPTY_REEXTRACT})), [publish]);

  return {state, open, close, refresh, select, openDeleteDialog, closeDeleteDialog, confirmDelete, startReextract, loadReview, approveReview, discardReview, closeReview};
}

export type CvManagerController = ReturnType<typeof useCvManagerState>;

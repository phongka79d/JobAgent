import {useCallback, useEffect, useRef, useState} from 'react';

import {defaultCvManagerApi, type CvManagerApi} from './api';
import type {CvManagerItem} from './types';

export type CvManagerSafeError = {code: string; summary: string};
export type CvManagerViewState = {
  phase: 'closed' | 'loading' | 'ready' | 'error';
  items: CvManagerItem[];
  selectedId: string | null;
  pendingByAttachment: Record<string, true>;
  errorsByAttachment: Record<string, CvManagerSafeError>;
  deleteTargetId: string | null;
};

const CLOSED: CvManagerViewState = {
  phase: 'closed', items: [], selectedId: null, pendingByAttachment: {}, errorsByAttachment: {}, deleteTargetId: null,
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
  const api: CvManagerApi = {...defaultCvManagerApi, ...options.api};
  const profileScope = options.profileId ?? 'legacy';
  const scopeRef = useRef(profileScope);
  const listControllerRef = useRef<AbortController | null>(null);
  const mutationControllersRef = useRef(new Map<string, AbortController>());
  const mutationInFlightRef = useRef(new Set<string>());
  const generationRef = useRef(0);
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

  return {state, open, close, refresh, select, openDeleteDialog, closeDeleteDialog, confirmDelete};
}

export type CvManagerController = ReturnType<typeof useCvManagerState>;

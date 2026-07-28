import {useCallback, useEffect, useMemo, useReducer, useRef} from 'react';

import {defaultProfileApi} from './api';
import type {
  ConversationDeleteResponse,
  ConversationListResponse,
  ConversationMutationResponse,
  ConversationSummary,
  ProfileDeleteResponse,
  ProfileDetail,
  ProfileListItem,
  ProfileListResponse,
  SelectionResponse,
} from './conversationTypes';
import type {PendingProfileBootstrap} from './types';

export type ProfileWorkspaceState = {
  phase: WorkspacePhase;
  profiles: ProfileListItem[];
  activeProfileId: string | null;
  selectedConversationId: string | null;
  conversations: ConversationSummary[];
  pending: ReadonlySet<string>;
  error: string | null;
};
export type WorkspacePhase = 'rehydrating' | 'ready' | 'error';
type LegacyProfileWorkspaceState = Omit<ProfileWorkspaceState, 'phase'> & {
  phase?: never;
};
export type ProfileWorkspaceApi = Pick<typeof defaultProfileApi,
  'fetchProfiles' | 'fetchProfileConversations' | 'activateProfile' |
  'updateProfile' | 'deleteProfile' | 'createProfileConversation' |
  'selectConversation' | 'deleteConversation'>;
export type ProfileWorkspaceAction =
  | {type: 'rehydrate/started'}
  | {type: 'rehydrate/succeeded'; snapshot: WorkspaceSnapshot}
  | {type: 'rehydrate/failed'; error: string}
  | {
      type: 'conversations/loaded';
      profileId: string;
      response: ConversationListResponse;
    }
  | {type: 'profile/activated'; response: SelectionResponse}
  | {type: 'profile/renamed'; response: ProfileDetail}
  | {type: 'profile/deleted'; response: ProfileDeleteResponse}
  | {
      type: 'conversation/created';
      profileId: string;
      response: ConversationMutationResponse;
    }
  | {type: 'conversation/selected'; response: ConversationMutationResponse}
  | {type: 'conversation/deleted'; response: ConversationDeleteResponse}
  | {type: 'workspace/bootstrapAdopted'; bootstrap: PendingProfileBootstrap}
  | {type: 'error/reset'}
  | {type: 'mutation/started'; key: string}
  | {type: 'mutation/finished'; key: string}
  | {type: 'mutation/failed'; key: string; error: string};

type WorkspaceSnapshot = {
  profiles: ProfileListResponse;
  conversations: ConversationListResponse;
};

function validateSnapshot(snapshot: WorkspaceSnapshot): WorkspaceSnapshot {
  const active = snapshot.profiles.active_profile_id;
  if (
    active !== null &&
    !snapshot.profiles.items.some((item) => item.id === active)
  ) {
    throw new Error('Workspace data did not match the active profile.');
  }
  const activeItems = snapshot.profiles.items.filter((item) => item.is_active);
  if (
    (active === null && activeItems.length !== 0) ||
    (active !== null &&
      (activeItems.length !== 1 || activeItems[0]?.id !== active))
  ) {
    throw new Error('Workspace data did not match the active profile.');
  }
  if (
    snapshot.conversations.items.some((item) => item.profile_id !== active)
  ) {
    throw new Error('Workspace data did not match the active profile.');
  }
  const selected = snapshot.conversations.items.filter(
    (item) => item.is_selected,
  );
  if (selected.length > 1) {
    throw new Error('Workspace data did not match the active profile.');
  }
  return snapshot;
}

function conversationsBelongToProfile(
  response: ConversationListResponse,
  profileId: string | null,
): boolean {
  return (
    response.items.every((item) => item.profile_id === profileId) &&
    response.items.filter((item) => item.is_selected).length <= 1
  );
}

function workspaceProjectionError(
  state: ProfileWorkspaceState,
): ProfileWorkspaceState {
  return {
    ...state,
    phase: 'error',
    conversations: [],
    selectedConversationId: null,
    error: 'Workspace data did not match the active profile.',
  };
}

export const initialProfileWorkspaceState: ProfileWorkspaceState = {
  phase: 'rehydrating',
  profiles: [], activeProfileId: null, selectedConversationId: null,
  conversations: [], pending: new Set(), error: null,
};

export function profileWorkspaceReducer(state: ProfileWorkspaceState, action: ProfileWorkspaceAction): ProfileWorkspaceState {
  switch (action.type) {
    case 'rehydrate/started':
      return {
        ...state,
        phase: 'rehydrating',
        conversations: [],
        selectedConversationId: null,
        error: null,
      };
    case 'rehydrate/succeeded': {
      const snapshot = validateSnapshot(action.snapshot);
      const selected = snapshot.conversations.items.find(
        (item) => item.is_selected,
      );
      return {
        ...state,
        phase: 'ready',
        profiles: snapshot.profiles.items,
        activeProfileId: snapshot.profiles.active_profile_id,
        conversations: snapshot.conversations.items,
        selectedConversationId: selected?.id ?? null,
        error: null,
      };
    }
    case 'rehydrate/failed':
      return {
        ...state,
        phase: 'error',
        conversations: [],
        selectedConversationId: null,
        error: action.error,
      };
    case 'conversations/loaded': {
      if (
        action.profileId !== state.activeProfileId ||
        !conversationsBelongToProfile(action.response, state.activeProfileId)
      ) {
        return state;
      }
      const selected = action.response.items.find((item) => item.is_selected);
      return {
        ...state,
        phase: 'ready',
        conversations: action.response.items,
        selectedConversationId: selected?.id ?? null,
        error: null,
      };
    }
    case 'profile/activated':
      if (
        action.response.conversation &&
        action.response.conversation.profile_id !== action.response.profile.id
      ) {
        return workspaceProjectionError(state);
      }
      return {
        ...state,
        phase: 'ready',
        activeProfileId: action.response.profile.id,
        profiles: state.profiles.map((item) =>
          item.id === action.response.profile.id
            ? {...item, ...action.response.profile, is_active: true}
            : {...item, is_active: false},
        ),
        selectedConversationId: action.response.conversation?.id ?? null,
        conversations: action.response.conversation ? [action.response.conversation] : [],
        error: action.response.warning?.summary ?? null,
      };
    case 'profile/renamed':
      return {
        ...state,
        profiles: state.profiles.map((item) =>
          item.id === action.response.id
            ? {
                ...item,
                display_name: action.response.display_name,
                updated_at: action.response.updated_at,
                last_opened_at: action.response.last_opened_at,
              }
            : item,
        ),
        error: null,
      };
    case 'profile/deleted': {
      const activeProfile = action.response.active_profile;
      const selected = action.response.selected_conversation;
      if (
        (activeProfile && !activeProfile.is_active) ||
        (selected && selected.profile_id !== activeProfile?.id)
      ) {
        return workspaceProjectionError(state);
      }
      const remaining = state.profiles.filter(
        (item) => item.id !== action.response.deleted_profile_id,
      );
      const hasActiveProfile = activeProfile
        ? remaining.some((item) => item.id === activeProfile.id)
        : false;
      return {
        ...state,
        profiles: activeProfile
          ? hasActiveProfile
            ? remaining.map((item) =>
                item.id === activeProfile.id
                  ? activeProfile
                  : {...item, is_active: false},
              )
            : [
                activeProfile,
                ...remaining.map((item) => ({...item, is_active: false})),
              ]
          : remaining.map((item) => ({...item, is_active: false})),
        activeProfileId: activeProfile?.id ?? null,
        selectedConversationId: selected?.id ?? null,
        conversations: selected ? [selected] : [],
        error: null,
      };
    }
    case 'conversation/created': {
      const selected = action.response.conversation;
      if (
        selected.profile_id !== action.profileId ||
        action.profileId !== state.activeProfileId
      ) {
        return state;
      }
      return {...state, selectedConversationId: selected.id, conversations: [selected, ...state.conversations.filter((item) => item.id !== selected.id).map((item) => ({...item, is_selected: false}))]};
    }
    case 'conversation/selected': {
      const selected = action.response.conversation;
      if (selected.profile_id !== state.activeProfileId) return state;
      const listed = state.conversations.some((item) => item.id === selected.id);
      return {
        ...state,
        selectedConversationId: selected.id,
        conversations: listed
          ? state.conversations.map((item) => item.id === selected.id ? selected : {...item, is_selected: false})
          : [selected, ...state.conversations.map((item) => ({...item, is_selected: false}))],
      };
    }
    case 'conversation/deleted': {
      const selected = action.response.selected_conversation;
      if (selected.profile_id !== state.activeProfileId) return state;
      const remaining = state.conversations.filter((item) => item.id !== action.response.deleted_conversation_id).map((item) => item.id === selected.id ? selected : {...item, is_selected: false});
      return {...state, selectedConversationId: selected.id, conversations: remaining.some((item) => item.id === selected.id) ? remaining : [selected, ...remaining]};
    }
    case 'workspace/bootstrapAdopted': {
      const {profile, conversation} = action.bootstrap;
      if (!profile.is_active || conversation.profile_id !== profile.id) {
        return workspaceProjectionError(state);
      }
      return {
        ...state,
        phase: 'ready',
        profiles: [
          profile,
          ...state.profiles
            .filter((item) => item.id !== profile.id)
            .map((item) => ({...item, is_active: false})),
        ],
        activeProfileId: profile.id,
        selectedConversationId: conversation.id,
        conversations: [{...conversation, is_selected: true}],
        error: null,
      };
    }
    case 'mutation/started': return {...state, pending: new Set([...state.pending, action.key]), error: null};
    case 'mutation/finished': { const pending = new Set(state.pending); pending.delete(action.key); return {...state, pending}; }
    case 'mutation/failed': return {...state, error: action.error};
    case 'error/reset': return {...state, error: null};
  }
}

export type ProfileWorkspaceController = {
  state: ProfileWorkspaceState | LegacyProfileWorkspaceState;
  activate: (profileId: string) => Promise<void>;
  createConversation: (profileId: string) => Promise<void>;
  selectConversation: (conversationId: string) => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<boolean>;
  renameProfile: (profileId: string, displayName: string) => Promise<boolean>;
  deleteProfile: (profileId: string) => Promise<boolean>;
  reload: () => Promise<void>;
  adoptBootstrap: (bootstrap: PendingProfileBootstrap) => void;
};

export function useProfileWorkspaceState(
  apiOverrides: Partial<ProfileWorkspaceApi> = {},
  interactionLocked = false,
): ProfileWorkspaceController {
  const api = useMemo(() => ({...defaultProfileApi, ...apiOverrides}), [
    apiOverrides.fetchProfiles,
    apiOverrides.fetchProfileConversations,
    apiOverrides.activateProfile,
    apiOverrides.updateProfile,
    apiOverrides.deleteProfile,
    apiOverrides.createProfileConversation,
    apiOverrides.selectConversation,
    apiOverrides.deleteConversation,
  ]);
  const [state, dispatch] = useReducer(profileWorkspaceReducer, initialProfileWorkspaceState);
  const pendingRef = useRef(new Set<string>());
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const invalidateAuthoritativeWork = useCallback(() => {
    requestRef.current += 1;
    abortRef.current?.abort();
    return requestRef.current;
  }, []);
  const mutate = useCallback(async <T,>(key: string, request: () => Promise<T>, action: (value: T) => ProfileWorkspaceAction) => {
    if (interactionLocked || pendingRef.current.has(key)) return false;
    const requestId = invalidateAuthoritativeWork();
    pendingRef.current.add(key); dispatch({type: 'mutation/started', key});
    try {
      const response = await request();
      if (requestId !== requestRef.current) return false;
      dispatch(action(response));
      return true;
    }
    catch (error) {
      if (requestId === requestRef.current) {
        dispatch({type: 'mutation/failed', key, error: error instanceof Error ? error.message : 'Request failed'});
      }
      return false;
    }
    finally { pendingRef.current.delete(key); dispatch({type: 'mutation/finished', key}); }
  }, [interactionLocked, invalidateAuthoritativeWork]);
  const activate = useCallback(async (profileId: string) => {
    const key = `activate:${profileId}`;
    if (interactionLocked || pendingRef.current.has(key)) return;
    const requestId = invalidateAuthoritativeWork();
    pendingRef.current.add(key);
    dispatch({type: 'mutation/started', key});
    try {
      const response = await api.activateProfile(profileId);
      if (requestId !== requestRef.current) return;
      dispatch({type: 'profile/activated', response});
      const conversations = await api.fetchProfileConversations(profileId, {limit: 50});
      if (requestId === requestRef.current) {
        dispatch({type: 'conversations/loaded', profileId, response: conversations});
      }
    } catch (error) {
      if (requestId === requestRef.current) {
        dispatch({type: 'mutation/failed', key, error: error instanceof Error ? error.message : 'Request failed'});
      }
    } finally {
      pendingRef.current.delete(key);
      dispatch({type: 'mutation/finished', key});
    }
  }, [api, interactionLocked, invalidateAuthoritativeWork]);
  const createConversation = useCallback(async (profileId: string) => {
    if (state.phase !== 'ready' || state.activeProfileId !== profileId) return;
    await mutate(`create:${profileId}`, () => api.createProfileConversation(profileId), (response) => ({type: 'conversation/created', profileId, response}));
  }, [api, mutate, state.activeProfileId, state.phase]);
  const selectConversation = useCallback(async (conversationId: string) => {
    await mutate(`select:${conversationId}`, () => api.selectConversation(conversationId), (response) => ({type: 'conversation/selected', response}));
  }, [api, mutate]);
  const deleteConversation = useCallback((conversationId: string) => mutate(`delete:${conversationId}`, () => api.deleteConversation(conversationId), (response) => ({type: 'conversation/deleted', response})), [api, mutate]);
  const renameProfile = useCallback(
    (profileId: string, displayName: string) =>
      mutate(
        `rename:${profileId}`,
        () => api.updateProfile(profileId, displayName),
        (response) => ({type: 'profile/renamed', response}),
      ),
    [api, mutate],
  );
  const deleteProfile = useCallback(
    (profileId: string) =>
      mutate(
        `delete-profile:${profileId}`,
        () => api.deleteProfile(profileId),
        (response) => ({type: 'profile/deleted', response}),
      ),
    [api, mutate],
  );
  const adoptBootstrap = useCallback((bootstrap: PendingProfileBootstrap) => {
    invalidateAuthoritativeWork();
    dispatch({type: 'workspace/bootstrapAdopted', bootstrap});
  }, [invalidateAuthoritativeWork]);
  const reload = useCallback(async () => {
    const requestId = invalidateAuthoritativeWork();
    const controller = new AbortController();
    abortRef.current = controller;
    dispatch({type: 'rehydrate/started'});
    try {
      const profiles = await api.fetchProfiles(controller.signal);
      if (requestId !== requestRef.current || controller.signal.aborted) return;
      const conversations = profiles.active_profile_id
        ? await api.fetchProfileConversations(
            profiles.active_profile_id,
            {limit: 50},
            controller.signal,
          )
        : {items: [], next_cursor: null};
      if (requestId !== requestRef.current || controller.signal.aborted) return;
      const snapshot = validateSnapshot({profiles, conversations});
      dispatch({type: 'rehydrate/succeeded', snapshot});
    } catch (error) {
      if (
        requestId === requestRef.current &&
        !controller.signal.aborted
      ) {
        dispatch({
          type: 'rehydrate/failed',
          error: error instanceof Error ? error.message : 'Request failed',
        });
      }
    }
  }, [api, invalidateAuthoritativeWork]);
  useEffect(() => {
    void reload();
    return () => {
      requestRef.current += 1;
      abortRef.current?.abort();
    };
  }, [reload]);
  return {state, activate, createConversation, selectConversation, deleteConversation, renameProfile, deleteProfile, reload, adoptBootstrap};
}

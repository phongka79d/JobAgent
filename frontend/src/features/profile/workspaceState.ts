import {useCallback, useEffect, useMemo, useReducer, useRef} from 'react';

import {defaultProfileApi} from './api';
import type {
  ConversationDeleteResponse,
  ConversationListResponse,
  ConversationMutationResponse,
  ConversationSummary,
  ProfileListItem,
  ProfileListResponse,
  SelectionResponse,
} from './conversationTypes';
import type {PendingProfileBootstrap} from './types';

export type ProfileWorkspaceState = {
  profiles: ProfileListItem[];
  activeProfileId: string | null;
  selectedConversationId: string | null;
  conversations: ConversationSummary[];
  pending: ReadonlySet<string>;
  error: string | null;
};
export type ProfileWorkspaceApi = Pick<typeof defaultProfileApi,
  'fetchProfiles' | 'fetchProfileConversations' | 'activateProfile' |
  'createProfileConversation' | 'selectConversation' | 'deleteConversation'>;
export type ProfileWorkspaceAction =
  | {type: 'profiles/loaded'; response: ProfileListResponse}
  | {type: 'conversations/loaded'; response: ConversationListResponse}
  | {type: 'profile/activated'; response: SelectionResponse}
  | {type: 'conversation/created'; response: ConversationMutationResponse}
  | {type: 'conversation/selected'; response: ConversationMutationResponse}
  | {type: 'conversation/deleted'; response: ConversationDeleteResponse}
  | {type: 'workspace/bootstrapAdopted'; bootstrap: PendingProfileBootstrap}
  | {type: 'error/reset'}
  | {type: 'mutation/started'; key: string}
  | {type: 'mutation/finished'; key: string}
  | {type: 'mutation/failed'; key: string; error: string};

export const initialProfileWorkspaceState: ProfileWorkspaceState = {
  profiles: [], activeProfileId: null, selectedConversationId: null,
  conversations: [], pending: new Set(), error: null,
};

export function profileWorkspaceReducer(state: ProfileWorkspaceState, action: ProfileWorkspaceAction): ProfileWorkspaceState {
  switch (action.type) {
    case 'profiles/loaded': {
      const activeChanged = state.activeProfileId !== action.response.active_profile_id;
      return {
        ...state,
        profiles: action.response.items,
        activeProfileId: action.response.active_profile_id,
        conversations: activeChanged ? [] : state.conversations,
        selectedConversationId: activeChanged ? null : state.selectedConversationId,
        error: null,
      };
    }
    case 'conversations/loaded': {
      const selected = action.response.items.find((item) => item.is_selected) ?? null;
      return {...state, conversations: action.response.items, selectedConversationId: selected?.id ?? null, error: null};
    }
    case 'profile/activated':
      return {
        ...state,
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
    case 'conversation/created': {
      const selected = action.response.conversation;
      return {...state, selectedConversationId: selected.id, conversations: [selected, ...state.conversations.filter((item) => item.id !== selected.id).map((item) => ({...item, is_selected: false}))]};
    }
    case 'conversation/selected': {
      const selected = action.response.conversation;
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
      const remaining = state.conversations.filter((item) => item.id !== action.response.deleted_conversation_id).map((item) => item.id === selected.id ? selected : {...item, is_selected: false});
      return {...state, selectedConversationId: selected.id, conversations: remaining.some((item) => item.id === selected.id) ? remaining : [selected, ...remaining]};
    }
    case 'workspace/bootstrapAdopted': {
      const {profile, conversation} = action.bootstrap;
      return {
        ...state,
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
  state: ProfileWorkspaceState;
  activate: (profileId: string) => Promise<void>;
  createConversation: (profileId: string) => Promise<void>;
  selectConversation: (conversationId: string) => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
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
    apiOverrides.createProfileConversation,
    apiOverrides.selectConversation,
    apiOverrides.deleteConversation,
  ]);
  const [state, dispatch] = useReducer(profileWorkspaceReducer, initialProfileWorkspaceState);
  const pendingRef = useRef(new Set<string>());
  const requestRef = useRef(0);
  const mutate = useCallback(async <T,>(key: string, request: () => Promise<T>, action: (value: T) => ProfileWorkspaceAction) => {
    if (interactionLocked || pendingRef.current.has(key)) return;
    pendingRef.current.add(key); dispatch({type: 'mutation/started', key});
    try { dispatch(action(await request())); }
    catch (error) { dispatch({type: 'mutation/failed', key, error: error instanceof Error ? error.message : 'Request failed'}); }
    finally { pendingRef.current.delete(key); dispatch({type: 'mutation/finished', key}); }
  }, [interactionLocked]);
  const activate = useCallback(async (profileId: string) => {
    const key = `activate:${profileId}`;
    if (interactionLocked || pendingRef.current.has(key)) return;
    pendingRef.current.add(key);
    dispatch({type: 'mutation/started', key});
    try {
      const response = await api.activateProfile(profileId);
      dispatch({type: 'profile/activated', response});
      dispatch({type: 'conversations/loaded', response: await api.fetchProfileConversations(profileId, {limit: 50})});
    } catch (error) {
      dispatch({type: 'mutation/failed', key, error: error instanceof Error ? error.message : 'Request failed'});
    } finally {
      pendingRef.current.delete(key);
      dispatch({type: 'mutation/finished', key});
    }
  }, [api, interactionLocked]);
  const createConversation = useCallback((profileId: string) => mutate(`create:${profileId}`, () => api.createProfileConversation(profileId), (response) => ({type: 'conversation/created', response})), [api, mutate]);
  const selectConversation = useCallback((conversationId: string) => mutate(`select:${conversationId}`, () => api.selectConversation(conversationId), (response) => ({type: 'conversation/selected', response})), [api, mutate]);
  const deleteConversation = useCallback((conversationId: string) => mutate(`delete:${conversationId}`, () => api.deleteConversation(conversationId), (response) => ({type: 'conversation/deleted', response})), [api, mutate]);
  const adoptBootstrap = useCallback((bootstrap: PendingProfileBootstrap) => {
    requestRef.current += 1;
    dispatch({type: 'workspace/bootstrapAdopted', bootstrap});
  }, []);
  const reload = useCallback(async () => {
    const requestId = ++requestRef.current;
    try {
      const profiles = await api.fetchProfiles();
      if (requestId !== requestRef.current) return;
      dispatch({type: 'profiles/loaded', response: profiles});
      if (profiles.active_profile_id) {
        const response = await api.fetchProfileConversations(profiles.active_profile_id, {limit: 50});
        if (requestId === requestRef.current) dispatch({type: 'conversations/loaded', response});
      }
    } catch (error) {
      if (requestId === requestRef.current) {
        dispatch({type: 'mutation/failed', key: 'reload', error: error instanceof Error ? error.message : 'Request failed'});
      }
    }
  }, [api]);
  useEffect(() => { void reload(); return () => { requestRef.current += 1; }; }, [reload]);
  return {state, activate, createConversation, selectConversation, deleteConversation, reload, adoptBootstrap};
}

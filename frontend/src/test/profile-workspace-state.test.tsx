import {act, renderHook, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {
  initialProfileWorkspaceState,
  profileWorkspaceReducer,
  useProfileWorkspaceState,
  type ProfileWorkspaceApi,
} from '../features/profile/workspaceState';
import {useWorkspaceLifecycle} from '../features/profile/useWorkspaceLifecycle';
import type {
  ConversationListResponse,
  ConversationMutationResponse,
  ProfileListResponse,
} from '../features/profile/conversationTypes';
import type {PendingProfileBootstrap} from '../features/profile/types';

const PROFILE_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const PROFILE_B = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const CONVERSATION_A = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const CONVERSATION_B = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';

const conversation = {
  id: CONVERSATION_A,
  profile_id: PROFILE_A,
  title: 'Chat mới',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  last_opened_at: '2026-01-01T00:00:00Z',
  is_selected: true,
};

const pendingProfile = {
  id: PROFILE_A,
  display_name: 'Ada.pdf',
  cv_filename: 'Ada.pdf',
  attachment_state: 'staged' as const,
  location: null,
  skill_tags: [],
  skill_count: 0,
  extraction_version: null,
  source_hash: null,
  state: 'pending' as const,
  setup_status: 'awaiting_extraction' as const,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  last_opened_at: '2026-01-01T00:00:00Z',
};

const readyProfile = {
  ...pendingProfile,
  id: PROFILE_B,
  display_name: 'Grace Hopper',
  cv_filename: 'grace.pdf',
  attachment_state: 'active' as const,
  extraction_version: 'v1',
  source_hash: 'source-b',
  state: 'ready' as const,
  setup_status: null,
  is_active: false,
};

const readyProfileDetail = {
  ...readyProfile,
  profile: {
    full_name: 'Grace Hopper',
    location: null,
    summary: 'Compiler engineer',
    current_title: 'Rear Admiral',
    total_experience_years: null,
    skills: [],
    experiences: [],
    education: [],
    languages: [],
    extraction_confidence: 1,
  },
  preferences: {
    target_roles: [],
    preferred_locations: [],
    acceptable_work_modes: [],
    target_seniority: [],
  },
  attachment: {
    id: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
    original_name: 'grace.pdf',
    mime_type: 'application/pdf' as const,
    size_bytes: 1024,
    page_count: 1,
    state: 'active' as const,
    failure_code: null,
  },
  selected_conversation_id: CONVERSATION_B,
};

const bootstrap: PendingProfileBootstrap = {
  profile: pendingProfile,
  conversation,
  start_extraction: true,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return {promise, resolve, reject};
}

function profile(id: string, isActive: boolean) {
  return {...readyProfile, id, is_active: isActive};
}

function conversationFor(id: string, profileId: string, isSelected: boolean) {
  return {...conversation, id, profile_id: profileId, is_selected: isSelected};
}

function createWorkspaceApi(input: {
  profiles: ProfileListResponse;
  conversations: ConversationListResponse;
}): Partial<ProfileWorkspaceApi> {
  return {
    fetchProfiles: vi.fn().mockResolvedValue(input.profiles),
    fetchProfileConversations: vi.fn().mockResolvedValue(input.conversations),
  };
}

function createSequencedWorkspaceApi(
  profiles: Array<Promise<ProfileListResponse>>,
): Partial<ProfileWorkspaceApi> {
  let index = 0;
  return {
    fetchProfiles: vi.fn(() => profiles[index++]),
    fetchProfileConversations: vi.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
    }),
  };
}

describe('profile workspace state', () => {
  it('applies the server-selected conversation after create', async () => {
    const response: ConversationMutationResponse = {conversation};
    const createProfileConversation = vi.fn().mockResolvedValue(response);
    const {result} = renderHook(() =>
      useProfileWorkspaceState({createProfileConversation}),
    );

    await act(async () => {
      await result.current.createConversation(PROFILE_A);
    });

    expect(createProfileConversation).toHaveBeenCalledWith(PROFILE_A);
    expect(result.current.state.selectedConversationId).toBe(CONVERSATION_A);
    expect(result.current.state.conversations).toEqual([conversation]);
  });

  it('suppresses mutations while interactionLocked is true', async () => {
    const createProfileConversation = vi.fn();
    const {result} = renderHook(() =>
      useProfileWorkspaceState({createProfileConversation}, true),
    );

    await act(async () => {
      await result.current.createConversation(PROFILE_A);
    });

    expect(createProfileConversation).not.toHaveBeenCalled();
    expect(result.current.state.pending.size).toBe(0);
  });

  it('keeps server data when a reload fails and exposes a safe error', async () => {
    const fetchProfiles = vi
      .fn()
      .mockRejectedValue(new Error('workspace unavailable'));
    const {result} = renderHook(() =>
      useProfileWorkspaceState({fetchProfiles}),
    );

    await waitFor(() => {
      expect(result.current.state.error).toBe('workspace unavailable');
    });
    expect(result.current.state.profiles).toEqual([]);
    expect(result.current.state.selectedConversationId).toBe(
      initialProfileWorkspaceState.selectedConversationId,
    );
  });

  it('uses only the server selected conversation when deleting', () => {
    const next = profileWorkspaceReducer(
      {...initialProfileWorkspaceState, conversations: [conversation]},
      {
        type: 'conversation/deleted',
        response: {
          deleted_conversation_id: CONVERSATION_A,
          selected_conversation: {...conversation, is_selected: true},
          replacement_conversation_id: null,
        },
      },
    );
    expect(next.selectedConversationId).toBe(CONVERSATION_A);
    expect(next.conversations[0]?.id).toBe(CONVERSATION_A);
  });

  it('adopts server bootstrap identity without activation or conversation creation', async () => {
    const activateProfile = vi.fn();
    const createProfileConversation = vi.fn();
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [],
      active_profile_id: null,
    });
    const {result} = renderHook(() =>
      useProfileWorkspaceState({
        fetchProfiles,
        activateProfile,
        createProfileConversation,
      }),
    );

    await waitFor(() => expect(fetchProfiles).toHaveBeenCalled());
    act(() => {
      result.current.adoptBootstrap(bootstrap);
    });

    expect(result.current.state.activeProfileId).toBe(PROFILE_A);
    expect(result.current.state.selectedConversationId).toBe(CONVERSATION_A);
    expect(result.current.state.profiles).toEqual([pendingProfile]);
    expect(result.current.state.conversations).toEqual([conversation]);
    expect(activateProfile).not.toHaveBeenCalled();
    expect(createProfileConversation).not.toHaveBeenCalled();
  });

  it('renames through the profile API and applies the returned display name', async () => {
    const updateProfile = vi.fn().mockResolvedValue({
      ...readyProfileDetail,
      display_name: 'Amazing Grace',
    });
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [readyProfile],
      active_profile_id: PROFILE_B,
    });
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const {result} = renderHook(() =>
      useProfileWorkspaceState({
        fetchProfiles,
        fetchProfileConversations,
        updateProfile,
      }),
    );
    await waitFor(() => expect(result.current.state.profiles).toHaveLength(1));

    await act(async () => {
      await result.current.renameProfile(PROFILE_B, 'Amazing Grace');
    });

    expect(updateProfile).toHaveBeenCalledWith(PROFILE_B, 'Amazing Grace');
    expect(result.current.state.profiles[0]?.display_name).toBe('Amazing Grace');
  });

  it('adopts the server-returned fallback profile after deletion', async () => {
    const serverFallback = {
      ...readyProfile,
      display_name: 'Grace Hopper (selected)',
      is_active: true,
      last_opened_at: '2026-01-02T00:00:00Z',
    };
    const selectedConversation = {
      ...conversation,
      id: CONVERSATION_B,
      profile_id: PROFILE_B,
    };
    const deleteProfile = vi.fn().mockResolvedValue({
      deleted_profile_id: PROFILE_A,
      active_profile: serverFallback,
      selected_conversation: selectedConversation,
    });
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [pendingProfile, readyProfile],
      active_profile_id: PROFILE_A,
    });
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [conversation],
      next_cursor: null,
    });
    const {result} = renderHook(() =>
      useProfileWorkspaceState({
        fetchProfiles,
        fetchProfileConversations,
        deleteProfile,
      }),
    );
    await waitFor(() => expect(result.current.state.profiles).toHaveLength(2));

    await act(async () => {
      await result.current.deleteProfile(PROFILE_A);
    });

    expect(deleteProfile).toHaveBeenCalledWith(PROFILE_A);
    expect(result.current.state.activeProfileId).toBe(PROFILE_B);
    expect(result.current.state.profiles).toEqual([serverFallback]);
    expect(result.current.state.selectedConversationId).toBe(CONVERSATION_B);
  });

  it('reports a failed profile deletion without changing server-owned state', async () => {
    const deleteProfile = vi.fn().mockRejectedValue(new Error('Delete blocked'));
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [readyProfile],
      active_profile_id: PROFILE_B,
    });
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const {result} = renderHook(() =>
      useProfileWorkspaceState({
        fetchProfiles,
        fetchProfileConversations,
        deleteProfile,
      }),
    );
    await waitFor(() => expect(result.current.state.profiles).toHaveLength(1));

    let succeeded: boolean | undefined;
    await act(async () => {
      succeeded = await result.current.deleteProfile(PROFILE_B);
    });

    expect(succeeded).toBe(false);
    expect(result.current.state.error).toBe('Delete blocked');
    expect(result.current.state.profiles).toEqual([readyProfile]);
  });

  it('publishes ready state only when every conversation belongs to the active profile', async () => {
    const api = createWorkspaceApi({
      profiles: {items: [profile('profile-a', true)], active_profile_id: 'profile-a'},
      conversations: {
        items: [conversationFor('conversation-b', 'profile-b', true)],
        next_cursor: null,
      },
    });
    const {result} = renderHook(() => useProfileWorkspaceState(api));

    await waitFor(() => expect(result.current.state.phase).toBe('error'));
    expect(result.current.state.conversations).toEqual([]);
    expect(result.current.state.selectedConversationId).toBeNull();
    expect(result.current.state.error).toBe('Workspace data did not match the active profile.');
  });

  it('ignores an older reload after a newer authoritative snapshot wins', async () => {
    const first = deferred<ProfileListResponse>();
    const second = deferred<ProfileListResponse>();
    const api = createSequencedWorkspaceApi([first.promise, second.promise]);
    const {result} = renderHook(() => useProfileWorkspaceState(api));

    act(() => { void result.current.reload(); });
    second.resolve({items: [profile('profile-b', true)], active_profile_id: 'profile-b'});
    await waitFor(() => expect(result.current.state.activeProfileId).toBe('profile-b'));
    first.resolve({items: [profile('profile-a', true)], active_profile_id: 'profile-a'});

    await waitFor(() => expect(result.current.state.activeProfileId).toBe('profile-b'));
  });

  it('rehydrates a persisted pageshow and removes the listener on cleanup', async () => {
    const reload = vi.fn(async () => undefined);
    const {unmount} = renderHook(() => useWorkspaceLifecycle(reload));
    window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    unmount();
    window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
    expect(reload).toHaveBeenCalledTimes(1);
  });
});

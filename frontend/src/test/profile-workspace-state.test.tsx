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
  is_active: true,
};

const readyProfileDetail = {
  ...readyProfile,
  profile: {
    full_name: 'Grace Hopper',
    location: null,
    phone: null,
    email: null,
    github_url: null,
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

function activationResponse(profileId: string, conversationId: string) {
  return {
    profile: {...readyProfileDetail, id: profileId, is_active: true},
    conversation: conversationFor(conversationId, profileId, true),
    warning: null,
  };
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
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [profile(PROFILE_A, true)],
      active_profile_id: PROFILE_A,
    });
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [conversation],
      next_cursor: null,
    });
    const {result} = renderHook(() =>
      useProfileWorkspaceState({
        createProfileConversation,
        fetchProfiles,
        fetchProfileConversations,
      }),
    );

    await waitFor(() => expect(result.current.state.activeProfileId).toBe(PROFILE_A));
    await act(async () => {
      await result.current.createConversation(PROFILE_A);
    });

    expect(createProfileConversation).toHaveBeenCalledWith(PROFILE_A);
    expect(result.current.state.selectedConversationId).toBe(CONVERSATION_A);
    expect(result.current.state.conversations).toEqual([conversation]);
  });

  it('rejects conversation creation when no active profile exists', async () => {
    const createProfileConversation = vi.fn().mockResolvedValue({conversation});
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [],
      active_profile_id: null,
    });
    const {result} = renderHook(() =>
      useProfileWorkspaceState({createProfileConversation, fetchProfiles}),
    );

    await waitFor(() => expect(result.current.state.phase).toBe('ready'));
    await act(async () => {
      await result.current.createConversation(PROFILE_A);
    });

    expect(createProfileConversation).not.toHaveBeenCalled();
    expect(result.current.state.selectedConversationId).toBeNull();
    expect(result.current.state.conversations).toEqual([]);
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
      {
        ...initialProfileWorkspaceState,
        activeProfileId: PROFILE_A,
        conversations: [conversation],
      },
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
      items: [pendingProfile, {...readyProfile, is_active: false}],
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

  it('returns false and ignores a stale mutation response after reload', async () => {
    const updateProfile = deferred<typeof readyProfileDetail>();
    const fetchProfiles = vi.fn().mockResolvedValue({
      items: [profile(PROFILE_A, true)],
      active_profile_id: PROFILE_A,
    });
    const fetchProfileConversations = vi.fn().mockResolvedValue({
      items: [conversation],
      next_cursor: null,
    });
    const updateProfileRequest = vi.fn(() => updateProfile.promise);
    const {result} = renderHook(() =>
      useProfileWorkspaceState({
        fetchProfiles,
        fetchProfileConversations,
        updateProfile: updateProfileRequest,
      }),
    );

    await waitFor(() => expect(result.current.state.activeProfileId).toBe(PROFILE_A));
    let renameResult!: Promise<boolean>;
    act(() => {
      renameResult = result.current.renameProfile(PROFILE_A, 'New name');
    });
    await act(async () => {
      await result.current.reload();
    });
    updateProfile.resolve({...readyProfileDetail, id: PROFILE_A, display_name: 'New name'});

    let succeeded: boolean | undefined;
    await act(async () => {
      succeeded = await renameResult;
    });
    expect(succeeded).toBe(false);
    expect(result.current.state.profiles[0]?.display_name).toBe(readyProfile.display_name);
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

  it('fails closed when profile deletion projects an inactive active profile', () => {
    const next = profileWorkspaceReducer(
      {
        ...initialProfileWorkspaceState,
        phase: 'ready',
        profiles: [profile(PROFILE_A, true), profile(PROFILE_B, false)],
        activeProfileId: PROFILE_A,
        conversations: [conversation],
        selectedConversationId: CONVERSATION_A,
      },
      {
        type: 'profile/deleted',
        response: {
          deleted_profile_id: PROFILE_A,
          active_profile: {...readyProfile, is_active: false},
          selected_conversation: conversationFor(CONVERSATION_B, PROFILE_B, true),
        },
      },
    );

    expect(next.phase).toBe('error');
    expect(next.conversations).toEqual([]);
    expect(next.selectedConversationId).toBeNull();
    expect(next.error).toBe('Workspace data did not match the active profile.');
  });

  it('fails closed when bootstrap projects an inactive profile', () => {
    const next = profileWorkspaceReducer(
      initialProfileWorkspaceState,
      {
        type: 'workspace/bootstrapAdopted',
        bootstrap: {
          ...bootstrap,
          profile: {...bootstrap.profile, is_active: false},
        },
      },
    );

    expect(next.phase).toBe('error');
    expect(next.conversations).toEqual([]);
    expect(next.selectedConversationId).toBeNull();
    expect(next.error).toBe('Workspace data did not match the active profile.');
  });

  it.each([
    {
      name: 'a flagged profile without an active profile id',
      profiles: {
        items: [profile(PROFILE_A, true)],
        active_profile_id: null,
      },
    },
    {
      name: 'an active profile id without a matching active flag',
      profiles: {
        items: [profile(PROFILE_A, false), profile(PROFILE_B, true)],
        active_profile_id: PROFILE_A,
      },
    },
    {
      name: 'multiple profiles flagged active',
      profiles: {
        items: [profile(PROFILE_A, true), profile(PROFILE_B, true)],
        active_profile_id: PROFILE_A,
      },
    },
  ])('rejects snapshots when $name', async ({profiles}) => {
    const api = createWorkspaceApi({
      profiles,
      conversations: {items: [], next_cursor: null},
    });
    const {result} = renderHook(() => useProfileWorkspaceState(api));

    await waitFor(() => expect(result.current.state.phase).toBe('error'));
    expect(result.current.state.conversations).toEqual([]);
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

  it('keeps activation authoritative over an in-flight reload', async () => {
    const initialProfiles: ProfileListResponse = {
      items: [profile(PROFILE_A, true), profile(PROFILE_B, false)],
      active_profile_id: PROFILE_A,
    };
    const reloadProfiles = deferred<ProfileListResponse>();
    let profileAConversationCalls = 0;
    const fetchProfiles = vi
      .fn()
      .mockResolvedValueOnce(initialProfiles)
      .mockImplementationOnce(() => reloadProfiles.promise);
    const fetchProfileConversations = vi.fn((profileId: string) => {
      if (profileId === PROFILE_B) {
        return Promise.resolve({
          items: [conversationFor(CONVERSATION_B, PROFILE_B, true)],
          next_cursor: null,
        });
      }
      if (profileAConversationCalls++ === 0) {
        return Promise.resolve({
          items: [conversationFor(CONVERSATION_A, PROFILE_A, true)],
          next_cursor: null,
        });
      }
      return Promise.resolve({
        items: [conversationFor(CONVERSATION_A, PROFILE_A, true)],
        next_cursor: null,
      });
    });
    const api = {
      fetchProfiles,
      fetchProfileConversations,
      activateProfile: vi
        .fn()
        .mockResolvedValue(activationResponse(PROFILE_B, CONVERSATION_B)),
    };
    const {result} = renderHook(() => useProfileWorkspaceState(api));

    await waitFor(() => expect(result.current.state.activeProfileId).toBe(PROFILE_A));
    act(() => { void result.current.reload(); });
    await waitFor(() => expect(fetchProfiles).toHaveBeenCalledTimes(2));

    await act(async () => {
      await result.current.activate(PROFILE_B);
    });
    expect(result.current.state.activeProfileId).toBe(PROFILE_B);
    expect(result.current.state.selectedConversationId).toBe(CONVERSATION_B);

    await act(async () => {
      reloadProfiles.resolve(initialProfiles);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(fetchProfileConversations).toHaveBeenCalledTimes(2);
    expect(result.current.state.activeProfileId).toBe(PROFILE_B);
    expect(result.current.state.conversations).toEqual([
      conversationFor(CONVERSATION_B, PROFILE_B, true),
    ]);
  });

  it('ignores a stale activation conversation response after a newer activation wins', async () => {
    const profiles: ProfileListResponse = {
      items: [profile(PROFILE_A, true), profile(PROFILE_B, false)],
      active_profile_id: PROFILE_A,
    };
    const staleConversation = deferred<ConversationListResponse>();
    let profileAConversationCalls = 0;
    const fetchProfileConversations = vi.fn((profileId: string) => {
      if (profileId === PROFILE_B) {
        return Promise.resolve({
          items: [conversationFor(CONVERSATION_B, PROFILE_B, true)],
          next_cursor: null,
        });
      }
      if (profileAConversationCalls++ === 0) {
        return Promise.resolve({
          items: [conversationFor(CONVERSATION_A, PROFILE_A, true)],
          next_cursor: null,
        });
      }
      return staleConversation.promise;
    });
    const api = {
      fetchProfiles: vi.fn().mockResolvedValue(profiles),
      fetchProfileConversations,
      activateProfile: vi.fn((profileId: string) =>
        Promise.resolve(
          activationResponse(
            profileId,
            profileId === PROFILE_A ? CONVERSATION_A : CONVERSATION_B,
          ),
        ),
      ),
    };
    const {result} = renderHook(() => useProfileWorkspaceState(api));

    await waitFor(() => expect(result.current.state.activeProfileId).toBe(PROFILE_A));
    act(() => { void result.current.activate(PROFILE_A); });
    await waitFor(() => expect(fetchProfileConversations).toHaveBeenCalledTimes(2));
    act(() => { void result.current.activate(PROFILE_B); });
    await waitFor(() => expect(result.current.state.activeProfileId).toBe(PROFILE_B));
    expect(result.current.state.conversations).toEqual([
      conversationFor(CONVERSATION_B, PROFILE_B, true),
    ]);

    staleConversation.resolve({
      items: [conversationFor(CONVERSATION_A, PROFILE_A, true)],
      next_cursor: null,
    });
    await waitFor(() => expect(result.current.state.activeProfileId).toBe(PROFILE_B));
    expect(result.current.state.conversations).toEqual([
      conversationFor(CONVERSATION_B, PROFILE_B, true),
    ]);
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

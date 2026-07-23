import {act, renderHook, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {
  initialProfileWorkspaceState,
  profileWorkspaceReducer,
  useProfileWorkspaceState,
} from '../features/profile/workspaceState';
import type {ConversationMutationResponse} from '../features/profile/conversationTypes';

const PROFILE_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const CONVERSATION_A = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const conversation = {
  id: CONVERSATION_A,
  profile_id: PROFILE_A,
  title: 'Chat mới',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  last_opened_at: '2026-01-01T00:00:00Z',
  is_selected: true,
};

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
});

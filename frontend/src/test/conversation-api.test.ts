import {expect, it} from 'vitest';

import {
  parseConversationDeleteResponse,
  parseConversationListResponse,
} from '../features/profile/conversationTypes';

const PROFILE_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1';
const CONVERSATION_ID = 'bbbbbbbb-cccc-4ddd-8eee-fffffffffff1';
const REPLACEMENT_ID = 'cccccccc-dddd-4eee-8fff-000000000001';
const NOW = '2026-07-23T10:00:00Z';
const conversation = {
  id: CONVERSATION_ID, profile_id: PROFILE_ID, title: 'Chat mới',
  created_at: NOW, updated_at: NOW, last_opened_at: NOW, is_selected: true,
};

it('parses a strict conversation list and rejects unknown fields', () => {
  expect(parseConversationListResponse({items: [conversation], next_cursor: null}).items[0]?.id).toBe(CONVERSATION_ID);
  expect(() => parseConversationListResponse({items: [], next_cursor: null, raw_text: 'secret'})).toThrow(/unexpected/);
});

it('parses the server-selected replacement after deletion', () => {
  const response = parseConversationDeleteResponse({
    deleted_conversation_id: CONVERSATION_ID,
    selected_conversation: {...conversation, id: REPLACEMENT_ID},
    replacement_conversation_id: REPLACEMENT_ID,
  });
  expect(response.selected_conversation.id).toBe(REPLACEMENT_ID);
});

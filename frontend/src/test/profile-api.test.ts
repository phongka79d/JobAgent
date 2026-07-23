import {afterEach, expect, it, vi} from 'vitest';

import {activateProfile} from '../features/profile/api';
import {parseProfileListResponse} from '../features/profile/conversationTypes';

const PROFILE_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1';
const NOW = '2026-07-23T10:00:00Z';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it('parses bounded profile metadata and rejects raw fields', () => {
  const parsed = parseProfileListResponse({
    items: [{
      id: PROFILE_ID, display_name: 'Ada', cv_filename: 'ada.pdf',
      attachment_state: 'active', location: 'London',
      skill_tags: [{key: 'python', label: 'Python'}], skill_count: 1,
      extraction_version: 'cv-v2', source_hash: 'hash-a', state: 'ready',
      is_active: true, created_at: NOW, updated_at: NOW, last_opened_at: NOW,
    }],
    active_profile_id: PROFILE_ID,
  });
  expect(parsed.items[0]?.location).toBe('London');
  expect(() => parseProfileListResponse({
    items: [], active_profile_id: null, storage_path: 'secret',
  })).toThrow(/unexpected/);
});

it('sends the profile id in the activation path', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    profile: {}, conversation: null, warning: null,
  }), {status: 200}));
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
  vi.stubGlobal('fetch', fetchMock);
  await expect(activateProfile(PROFILE_ID)).rejects.toThrow();
  expect(fetchMock.mock.calls[0]?.[0]).toContain(`/api/profiles/${PROFILE_ID}/activate`);
});

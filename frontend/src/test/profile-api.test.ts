import {afterEach, expect, it, vi} from 'vitest';

import {activateProfile} from '../features/profile/api';
import {
  parseProfileDetail,
  parseProfileListResponse,
} from '../features/profile/conversationTypes';
import {parseCvUploadResponse} from '../features/profile/types';

const PROFILE_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeee1';
const CONVERSATION_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2';
const ATTACHMENT_ID = 'cccccccc-cccc-4ccc-8ccc-ccccccccccc3';
const NOW = '2026-07-23T10:00:00Z';

const pendingProfile = {
  id: PROFILE_ID,
  display_name: 'Ada.pdf',
  cv_filename: 'Ada.pdf',
  attachment_state: 'staged',
  location: null,
  skill_tags: [],
  skill_count: 0,
  extraction_version: null,
  source_hash: null,
  state: 'pending',
  setup_status: 'awaiting_extraction',
  is_active: true,
  created_at: NOW,
  updated_at: NOW,
  last_opened_at: NOW,
} as const;

const conversation = {
  id: CONVERSATION_ID,
  profile_id: PROFILE_ID,
  title: 'Chat mới',
  created_at: NOW,
  updated_at: NOW,
  last_opened_at: NOW,
  is_selected: true,
} as const;

const attachment = {
  id: ATTACHMENT_ID,
  original_name: 'Ada.pdf',
  mime_type: 'application/pdf',
  size_bytes: 1024,
  page_count: 1,
  state: 'staged',
  failure_code: null,
} as const;

function pendingUpload(
  outcome: 'new_pending' | 'retry_pending' | 'existing_pending' = 'new_pending',
  start_extraction = true,
) {
  return {
    attachment,
    outcome,
    profile: null,
    draft: null,
    bootstrap: {profile: pendingProfile, conversation, start_extraction},
  };
}

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
      extraction_version: 'cv-v2', source_hash: 'hash-a', state: 'ready', setup_status: null,
      is_active: true, created_at: NOW, updated_at: NOW, last_opened_at: NOW,
    }],
    active_profile_id: PROFILE_ID,
  });
  expect(parsed.items[0]?.location).toBe('London');
  expect(() => parseProfileListResponse({
    items: [], active_profile_id: null, storage_path: 'secret',
  })).toThrow(/unexpected/);
});

it('parses ready profile detail with the lifecycle setup field', () => {
  const parsed = parseProfileDetail({
    id: PROFILE_ID,
    display_name: 'Ada',
    cv_filename: 'Ada.pdf',
    attachment_state: 'active',
    location: 'London',
    skill_tags: [],
    skill_count: 0,
    extraction_version: 'cv-v2',
    source_hash: 'hash-a',
    state: 'ready',
    setup_status: null,
    is_active: true,
    created_at: NOW,
    updated_at: NOW,
    last_opened_at: NOW,
    profile: {
      full_name: 'Ada Lovelace',
      location: 'London',
      summary: 'Engineer',
      current_title: 'Engineer',
      total_experience_years: 5,
      skills: [],
      experiences: [],
      education: [],
      languages: [],
      extraction_confidence: 0.9,
    },
    preferences: {
      target_roles: [],
      preferred_locations: [],
      acceptable_work_modes: [],
      target_seniority: [],
    },
    attachment: {...attachment, state: 'active'},
    selected_conversation_id: CONVERSATION_ID,
  });
  expect(parsed.setup_status).toBeNull();
  expect(parsed.selected_conversation_id).toBe(CONVERSATION_ID);
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

it('strictly parses all pending bootstrap outcomes and safe nullable metadata', () => {
  for (const outcome of ['new_pending', 'retry_pending', 'existing_pending'] as const) {
    const parsed = parseCvUploadResponse(
      pendingUpload(outcome, outcome !== 'existing_pending'),
    );
    expect(parsed.outcome).toBe(outcome);
    expect(parsed.bootstrap?.profile).toEqual(pendingProfile);
    expect(parsed.bootstrap?.conversation).toEqual(conversation);
    expect(parsed.bootstrap?.start_extraction).toBe(outcome !== 'existing_pending');
  }
});

it('parses ready upload outcomes without a bootstrap', () => {
  for (const outcome of ['existing_active', 'existing_profile'] as const) {
    const parsed = parseCvUploadResponse({
      attachment: {
        ...attachment,
        state: outcome === 'existing_active' ? 'active' : 'archived',
      },
      outcome,
      profile: {present: true, profile_id: PROFILE_ID, current_title: 'Engineer'},
      draft: null,
      bootstrap: null,
    });
    expect(parsed.outcome).toBe(outcome);
    expect(parsed.bootstrap).toBeNull();
    expect(parsed.profile?.profile_id).toBe(PROFILE_ID);
  }
});

it('rejects inconsistent or raw pending bootstrap fields', () => {
  expect(() => parseCvUploadResponse({...pendingUpload(), bootstrap: null})).toThrow();
  expect(() =>
    parseCvUploadResponse(pendingUpload('new_pending', false)),
  ).toThrow();
  expect(() =>
    parseCvUploadResponse({
      ...pendingUpload(),
      bootstrap: {
        ...pendingUpload().bootstrap,
        conversation: {...conversation, profile_id: ATTACHMENT_ID},
      },
    }),
  ).toThrow();
  expect(() =>
    parseCvUploadResponse({
      ...pendingUpload(),
      bootstrap: {
        ...pendingUpload().bootstrap,
        conversation: {...conversation, is_selected: 'yes'},
      },
    }),
  ).toThrow(/is_selected/);
  expect(() =>
    parseCvUploadResponse({
      ...pendingUpload(),
      bootstrap: {
        ...pendingUpload().bootstrap,
        profile: {...pendingProfile, location: 'Invented'},
      },
    }),
  ).toThrow();
  expect(() =>
    parseCvUploadResponse({
      ...pendingUpload(),
      bootstrap: {
        ...pendingUpload().bootstrap,
        profile: {...pendingProfile, raw_profile_json: {summary: 'secret'}},
      },
    }),
  ).toThrow(/unexpected/);
  expect(() =>
    parseCvUploadResponse({
      ...pendingUpload(),
      bootstrap: {
        ...pendingUpload().bootstrap,
        profile: {...pendingProfile, attachment_state: 'failed'},
      },
    }),
  ).toThrow(/inconsistent/);
  expect(() =>
    parseCvUploadResponse({
      attachment: {...attachment, state: 'active'},
      outcome: 'existing_active',
      profile: null,
      draft: null,
      bootstrap: null,
    }),
  ).toThrow(/profile/);
});

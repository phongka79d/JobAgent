import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  cvFileUrl,
  deleteCv,
  fetchCvManager,
} from '../features/cv-manager/api';
import {
  parseCvManagerItem,
  parseCvManagerListResponse,
} from '../features/cv-manager/types';
import type {
  CvManagerItem,
  CvManagerListResponse,
} from '../features/cv-manager/types';

const ACTIVE_CV_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const ACTIVE_PROFILE_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const FAILED_UNOWNED_CV_ID = '11111111-2222-4333-8444-555555555555';
const TS = '2026-07-13T12:00:00.000Z';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function activeProfileOwnedItem(): CvManagerItem {
  return {
    id: ACTIVE_CV_ID,
    original_name: 'resume.pdf',
    state: 'active',
    failure_code: null,
    page_count: 4,
    file_available: true,
    profile_id: ACTIVE_PROFILE_ID,
    profile_display_name: 'Profile A',
    profile_state: 'ready',
    is_active_profile: true,
    allowed_actions: ['preview', 'download', 'reextract'],
    created_at: TS,
    updated_at: TS,
  };
}

function unownedFailedItem(): CvManagerItem {
  return {
    id: FAILED_UNOWNED_CV_ID,
    original_name: 'failed-upload.pdf',
    state: 'failed',
    failure_code: 'EXTRACTION_FAILED',
    page_count: null,
    file_available: false,
    profile_id: null,
    profile_display_name: null,
    profile_state: null,
    is_active_profile: false,
    allowed_actions: ['delete_cv'],
    created_at: TS,
    updated_at: TS,
  };
}

function exactResponse(
  overrides: Partial<CvManagerListResponse> = {},
): CvManagerListResponse {
  return {
    items: [activeProfileOwnedItem()],
    ...overrides,
  };
}

describe('CV Manager exact DTO parsing', () => {
  it('accepts every server-projected action without inferring or dropping it', () => {
    const parsed = parseCvManagerItem({
      ...activeProfileOwnedItem(),
      allowed_actions: ['preview'],
    });
    expect(parsed.allowed_actions).toEqual(['preview']);
  });

  it('parses a profile-owned active fixture and preserves server actions', () => {
    const parsed = parseCvManagerListResponse(exactResponse());

    expect(parsed.items[0]).toEqual(activeProfileOwnedItem());
    expect(parsed.items[0]?.allowed_actions).toEqual([
      'preview',
      'download',
      'reextract',
    ]);
    expect(parsed.items[0]?.allowed_actions).not.toContain('delete_cv');
  });

  it('parses the truly unowned failed delete fixture', () => {
    const parsed = parseCvManagerItem(unownedFailedItem());

    expect(parsed.profile_id).toBeNull();
    expect(parsed.profile_display_name).toBeNull();
    expect(parsed.profile_state).toBeNull();
    expect(parsed.allowed_actions).toEqual(['delete_cv']);
  });

  it.each([
    ['top-level extra key', {...exactResponse(), extra: true}],
    [
      'item extra key',
      {
        items: [
          {...activeProfileOwnedItem(), extra: true},
        ],
      },
    ],
    [
      'storage_path',
      {
        items: [
          {...activeProfileOwnedItem(), storage_path: '/private/path'},
        ],
      },
    ],
    [
      'file_hash',
      {
        items: [
          {...activeProfileOwnedItem(), file_hash: 'private-hash'},
        ],
      },
    ],
    [
      'invalid UUID',
      {
        items: [
          {...activeProfileOwnedItem(), id: 'not-a-uuid'},
        ],
      },
    ],
    [
      'timezone-naive timestamp',
      {
        items: [
          {...activeProfileOwnedItem(), created_at: '2026-07-13T12:00:00'},
        ],
      },
    ],
    [
      'invalid timestamp',
      {
        items: [
          {...activeProfileOwnedItem(), updated_at: 'not-a-timestamp'},
        ],
      },
    ],
    [
      'invalid state',
      {
        items: [
          {...activeProfileOwnedItem(), state: 'ready'},
        ],
      },
    ],
    [
      'invalid action',
      {
        items: [
          {...activeProfileOwnedItem(), allowed_actions: ['infer']},
        ],
      },
    ],
    [
      'duplicate action',
      {
        items: [
          {
            ...activeProfileOwnedItem(),
            allowed_actions: ['preview', 'preview'],
          },
        ],
      },
    ],
    [
      'non-positive page_count',
      {
        items: [
          {...activeProfileOwnedItem(), page_count: 0},
        ],
      },
    ],
    [
      'non-integer page_count',
      {
        items: [
          {...activeProfileOwnedItem(), page_count: 1.5},
        ],
      },
    ],
    [
      'empty original_name',
      {
        items: [
          {...activeProfileOwnedItem(), original_name: '  '},
        ],
      },
    ],
    [
      'empty profile_display_name',
      {
        items: [
          {...activeProfileOwnedItem(), profile_display_name: ''},
        ],
      },
    ],
    [
      'invalid failure_code nullable type',
      {
        items: [
          {...activeProfileOwnedItem(), failure_code: 42},
        ],
      },
    ],
    [
      'invalid page_count nullable type',
      {
        items: [
          {...activeProfileOwnedItem(), page_count: '4'},
        ],
      },
    ],
    [
      'invalid profile_id nullable type',
      {
        items: [
          {...activeProfileOwnedItem(), profile_id: 42},
        ],
      },
    ],
    [
      'invalid profile_display_name nullable type',
      {
        items: [
          {
            ...activeProfileOwnedItem(),
            profile_display_name: 42,
          },
        ],
      },
    ],
    [
      'invalid profile_state nullable type',
      {
        items: [
          {
            ...activeProfileOwnedItem(),
            profile_state: 'unknown',
          },
        ],
      },
    ],
  ])('rejects %s', (_label, rawPayload) => {
    expect(() => parseCvManagerListResponse(rawPayload)).toThrow();
  });
});

describe('CV Manager API transport', () => {
  it('sends the exact GET request and parses the strict response', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
    const signal = new AbortController().signal;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(exactResponse()), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchCvManager(signal)).resolves.toEqual(exactResponse());
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/cvs',
      expect.objectContaining({
        method: 'GET',
        headers: {Accept: 'application/json'},
        signal,
      }),
    );
  });

  it('maps invalid JSON and invalid success payloads to the safe payload error', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('{bad json', {status: 200}))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({...exactResponse(), extra: true}), {
          status: 200,
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchCvManager()).rejects.toMatchObject({
      status: 200,
      code: 'INVALID_CV_MANAGER_PAYLOAD',
    });
    await expect(fetchCvManager()).rejects.toMatchObject({
      status: 200,
      code: 'INVALID_CV_MANAGER_PAYLOAD',
    });
  });

  it('uses parseErrorBody for non-OK responses', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {code: 'CV_LIST_FAILED', summary: 'List unavailable'},
          }),
          {status: 503},
        ),
      ),
    );

    await expect(fetchCvManager()).rejects.toMatchObject({
      status: 503,
      code: 'CV_LIST_FAILED',
      summary: 'List unavailable',
    });
  });

  it('sends DELETE with the exact request and only accepts 204', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
    const signal = new AbortController().signal;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, {status: 200}))
      .mockResolvedValueOnce(new Response(null, {status: 204}));
    vi.stubGlobal('fetch', fetchMock);

    await expect(deleteCv(FAILED_UNOWNED_CV_ID, signal)).rejects.toMatchObject({
      status: 200,
      code: 'HTTP_ERROR',
      summary: 'HTTP 200',
    });
    await expect(deleteCv(FAILED_UNOWNED_CV_ID, signal)).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `http://api.test/api/cvs/${FAILED_UNOWNED_CV_ID}`,
      expect.objectContaining({
        method: 'DELETE',
        headers: {Accept: 'application/json'},
        signal,
      }),
    );
  });

  it('encodes IDs and uses the exact inline or attachment disposition', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test/');

    expect(cvFileUrl('id/with space', 'inline')).toBe(
      'http://api.test/api/cvs/id%2Fwith%20space/file?disposition=inline',
    );
    expect(cvFileUrl(ACTIVE_CV_ID, 'attachment')).toBe(
      `http://api.test/api/cvs/${ACTIVE_CV_ID}/file?disposition=attachment`,
    );
  });
});

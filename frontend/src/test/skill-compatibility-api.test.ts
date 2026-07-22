import {afterEach, describe, expect, it, vi} from 'vitest';

import {fetchSelectedJobSkillMap} from '../features/jobs/api';
import {parseSelectedJobSkillMap} from '../features/jobs/types';

const JOB_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const CV_ID = '11111111-2222-4333-8444-555555555555';
const TS = '2024-08-01T12:00:00.000Z';

function assertion(
  canonicalKey: string,
  displayName: string,
  confidence = 0.8,
) {
  return {
    canonical_key: canonicalKey,
    display_name: displayName,
    confidence,
    evidence: [`Evidence for ${displayName}`],
  };
}

function readyPayload() {
  return {
    status: 'ready',
    code: null,
    summary: 'Selected map is ready.',
    rebuild_instruction: null,
    candidate: {
      id: 'active',
      attachment_id: CV_ID,
      current_title: 'Điều phối viên',
      revision: TS,
    },
    job: {
      id: JOB_ID,
      title: 'Campaign Operations',
      company: 'Synthetic Co',
      revision: TS,
    },
    items: [
      {
        match_type: 'direct',
        requirement: 'required',
        strength: 1,
        candidate_skill: assertion('audience_research', 'Audience Research', 0.9),
        job_skill: assertion('audience_research', 'Nghiên cứu đối tượng'),
        relationship: null,
      },
      {
        match_type: 'related',
        requirement: 'preferred',
        strength: 0.6,
        candidate_skill: assertion('service_design_research', 'Service Design/Research'),
        job_skill: assertion('customer_discovery', 'Customer Discovery'),
        relationship: {
          from_key: 'service_design_research',
          to_key: 'customer_discovery',
          weight: 0.75,
          source: 'seed',
        },
      },
    ],
    counts: {
      direct: 1,
      related: 1,
      missing_required: 0,
      missing_preferred: 0,
      candidate_only: 0,
    },
    checked_at: TS,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('selected skill-map strict parser', () => {
  it('preserves backend source labels and exact status coupling', () => {
    const parsed = parseSelectedJobSkillMap(readyPayload());

    expect(parsed.status).toBe('ready');
    expect(parsed.items[0]!.candidate_skill?.display_name).toBe('Audience Research');
    expect(parsed.items[0]!.job_skill?.display_name).toBe('Nghiên cứu đối tượng');
    expect(parsed.items[1]!.candidate_skill?.display_name).toBe(
      'Service Design/Research',
    );
    expect(parsed.counts).toEqual(readyPayload().counts);
  });

  it.each([
    {...readyPayload(), raw_content: 'forbidden'},
    {
      ...readyPayload(),
      items: [{...readyPayload().items[0], strength: 0.6}],
    },
    {
      ...readyPayload(),
      counts: {...readyPayload().counts, direct: 0},
    },
    {
      ...readyPayload(),
      items: [
        {
          ...readyPayload().items[1],
          relationship: null,
        },
      ],
      counts: {...readyPayload().counts, direct: 0},
    },
    {
      ...readyPayload(),
      status: 'stale',
      code: 'NEO4J_REBUILD_REQUIRED',
      rebuild_instruction: 'Run rebuild.',
    },
  ])('rejects malformed shape or coupling %#', (payload) => {
    expect(() => parseSelectedJobSkillMap(payload)).toThrow();
  });

  it('rejects more than 200 items', () => {
    const item = readyPayload().items[0];
    const items = Array.from({length: 201}, () => ({...item}));
    expect(() =>
      parseSelectedJobSkillMap({
        ...readyPayload(),
        items,
        counts: {...readyPayload().counts, direct: 201, related: 0},
      }),
    ).toThrow(/200/);
  });

  it('rejects malformed UUID v4 and timezone-aware UTC fields', () => {
    const payloads = [
      {
        ...readyPayload(),
        candidate: {...readyPayload().candidate, attachment_id: 'not-a-uuid'},
      },
      {
        ...readyPayload(),
        job: {...readyPayload().job, id: 'not-a-uuid'},
      },
      {
        ...readyPayload(),
        candidate: {
          ...readyPayload().candidate,
          revision: '2024-08-01T12:00:00',
        },
      },
      {
        ...readyPayload(),
        job: {
          ...readyPayload().job,
          revision: '2024-08-01T12:00:00+07:00',
        },
      },
      {...readyPayload(), checked_at: 'not-a-date'},
    ];

    for (const payload of payloads) {
      expect(() => parseSelectedJobSkillMap(payload)).toThrow();
    }
  });

  it('accepts stale/unavailable only with empty items and exact guidance', () => {
    const emptyCounts = {
      direct: 0,
      related: 0,
      missing_required: 0,
      missing_preferred: 0,
      candidate_only: 0,
    };
    expect(
      parseSelectedJobSkillMap({
        ...readyPayload(),
        status: 'stale',
        code: 'NEO4J_REBUILD_REQUIRED',
        rebuild_instruction: 'Run rebuild.',
        items: [],
        counts: emptyCounts,
      }).status,
    ).toBe('stale');
    expect(
      parseSelectedJobSkillMap({
        ...readyPayload(),
        status: 'unavailable',
        code: 'NEO4J_UNAVAILABLE',
        rebuild_instruction: null,
        items: [],
        counts: emptyCounts,
      }).status,
    ).toBe('unavailable');
  });
});

describe('selected skill-map transport', () => {
  it('uses one read-only GET and strictly parses the response', async () => {
    const previousBaseUrl = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation of Vite env
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(readyPayload()), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    try {
      const result = await fetchSelectedJobSkillMap(JOB_ID);

      expect(result.status).toBe('ready');
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(String(url)).toContain(
        `/api/observability/skill-map?job_id=${encodeURIComponent(JOB_ID)}`,
      );
      expect(init).toMatchObject({method: 'GET'});
      expect(String(url)).not.toContain('evaluate');
    } finally {
      // @ts-expect-error restore test mutation
      import.meta.env.VITE_API_BASE_URL = previousBaseUrl;
    }
  });

  it('rejects a response for a different Job than the requested cache key', async () => {
    const previousBaseUrl = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation of Vite env
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';
    const payload = readyPayload();
    payload.job.id = '99999999-aaaa-4bbb-8ccc-dddddddddddd';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: {'Content-Type': 'application/json'},
        }),
      ),
    );

    try {
      await expect(fetchSelectedJobSkillMap(JOB_ID)).rejects.toMatchObject({
        code: 'INVALID_SKILL_MAP_PAYLOAD',
      });
    } finally {
      // @ts-expect-error restore test mutation
      import.meta.env.VITE_API_BASE_URL = previousBaseUrl;
    }
  });
});

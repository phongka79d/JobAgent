import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  parseTailoringSessionDetail,
  parseTailoringSessionList,
  parseTailoringMutationResponse,
  parseTailoringSseFrame,
} from '../features/cv-tailoring/types';
import {streamCreateTailoringSession} from '../features/cv-tailoring/api';
import {
  streamChatTurn,
  streamConversationTurn,
} from '../lib/api/chat';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const PROFILE_ID = '22222222-2222-4222-8222-222222222222';
const VERSION_ID = '33333333-3333-4333-8333-333333333333';
const RUN_ID = '44444444-4444-4444-8444-444444444444';
const NOW = '2026-07-26T00:00:00Z';

const summary = {
  id: SESSION_ID,
  profile_id: PROFILE_ID,
  job_label: null,
  instruction: 'Focus the summary',
  template_version: 'latex-cv-v1',
  state: 'ready',
  currentness: 'current',
  latest_version_number: 1,
  error_code: null,
  created_at: NOW,
  updated_at: NOW,
};

const detail = {
  session: summary,
  versions: [
    {
      id: VERSION_ID,
      version_number: 1,
      parent_version_id: null,
      created_by: 'ai',
      page_count: 1,
      page_warning: null,
      created_at: NOW,
    },
  ],
  selected_version: {
    id: VERSION_ID,
    version_number: 1,
    parent_version_id: null,
    created_by: 'ai',
    page_count: 1,
    page_warning: null,
    created_at: NOW,
  },
  content: {
    header: {
      full_name: 'Synthetic Candidate',
      location: null,
      phone: null,
      email: null,
      github_url: null,
    },
    sections: [
      {
        id: 'summary',
        ordinal: 0,
        heading: 'Summary',
        kind: 'summary',
        items: [
          {
            id: 'summary:item',
            source_entry_id: 'summary:source',
            title: null,
            subtitle: null,
            date_text: null,
            location: null,
            body: {text: 'Grounded text', source_fact_ids: ['sf_123']},
            bullets: [],
            attributes: [],
          },
        ],
      },
    ],
  },
  evidence: [],
  latest_run: {
    id: RUN_ID,
    state: 'completed',
    error_code: null,
    activities: [],
  },
  source_available: true,
  pdf_available: true,
};

describe('CV tailoring strict contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('accepts the exact list/detail shapes and rejects extras or LaTeX JSON', () => {
    expect(parseTailoringSessionList({items: [summary]}).items).toHaveLength(1);
    expect(parseTailoringSessionDetail(detail).content?.sections[0]?.heading).toBe(
      'Summary',
    );
    expect(() => parseTailoringSessionList({items: [summary], storage_path: 'x'}))
      .toThrow();
    expect(() =>
      parseTailoringSessionDetail({
        ...detail,
        content: {
          ...detail.content,
          sections: [
            {
              ...detail.content.sections[0],
              items: [
                {
                  ...detail.content.sections[0]!.items[0],
                  body: {
                    text: '\\documentclass{article}',
                    source_fact_ids: ['sf_123'],
                  },
                },
              ],
            },
          ],
        },
      }),
    ).toThrow();
  });

  it('parses no-change mutation identity and strictly couples stream outcomes', () => {
    expect(parseTailoringMutationResponse({outcome: 'no_change', session_id: SESSION_ID, version_id: VERSION_ID, version_number: 1, currentness: 'current'})).toMatchObject({outcome: 'no_change', version_id: VERSION_ID});
    const envelope = {event_id: '66666666-6666-4666-8666-666666666666', run_id: RUN_ID, timestamp: NOW, event: 'run_completed', payload: {state: 'completed', outcome: 'no_change', version_id: VERSION_ID, version_number: 1}};
    expect(parseTailoringSseFrame({id: envelope.event_id, event: 'run_completed', data: JSON.stringify(envelope)})).toMatchObject({ok: true, event: envelope});
    expect(parseTailoringSseFrame({id: envelope.event_id, event: 'run_completed', data: JSON.stringify({...envelope, payload: {state: 'completed', version_id: VERSION_ID, version_number: 1}})}).ok).toBe(false);
  });

  it('validates the creation session header before consuming SSE', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('', {
        status: 200,
        headers: {'Content-Type': 'text/event-stream'},
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const onSessionId = vi.fn();
    await expect(
      streamCreateTailoringSession(
        {job_id: null, instruction: 'Focus the summary'},
        {onEvent: vi.fn(), onSessionId},
      ),
    ).rejects.toMatchObject({code: 'INVALID_TAILORING_SESSION_HEADER'});
    expect(onSessionId).not.toHaveBeenCalled();
  });

  it('serializes selected_job_id as UUID or null without cached JD data', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
    const fetchMock = vi
      .fn()
      .mockImplementation(async () =>
        new Response('', {
          status: 200,
          headers: {'Content-Type': 'text/event-stream'},
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    await streamChatTurn({message: 'Tailor', selected_job_id: null}, {onEvent: vi.fn()});
    await streamConversationTurn(
      SESSION_ID,
      {message: 'Tailor', selected_job_id: VERSION_ID},
      {onEvent: vi.fn()},
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      message: 'Tailor',
      attachment_ids: [],
      selected_job_id: null,
    });
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      message: 'Tailor',
      attachment_ids: [],
      selected_job_id: VERSION_ID,
    });
    expect(String(fetchMock.mock.calls[1]?.[1]?.body)).not.toContain('raw_content');
  });
});

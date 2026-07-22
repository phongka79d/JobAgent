/**
 * Match card + durable history projection tests (Plan 6 Batch04 04A).
 * Strict compact parsing, backend order, display-only rounding, safe URL,
 * skill groups, unavailable components, effective weights, terminal rehydrate,
 * restart hydration, exact-one rendering, prior saved-job/approval labels.
 */
import type {ReactElement} from 'react';
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ChatPage, type ChatPageDeps} from '../features/chat/ChatPage';
import {ChatMessages} from '../features/chat/components/ChatMessages';
import {
  matchJobsResultForTools,
  toolsForAssistantDisplay,
} from '../features/chat/components/ChatMessageRow';
import {friendlyToolLabel} from '../features/chat/components/ChatToolActivity';
import {
  hydrateFromHistoryPage,
  rehydrateWithDurableTruth,
  toolViewToActivity,
} from '../features/chat/history';
import {
  chatReducer,
  createInitialChatState,
} from '../features/chat/reducer';
import type {
  HistoryPage,
  JsonObject,
  SseEvent,
  ToolExecutionView,
  ToolResult,
} from '../features/chat/types';
import {parseSseEventData} from '../features/chat/types';
import {MatchCard} from '../features/jobs/MatchCard';
import {
  formatDisplayScore,
  parseMatchJobsResultData,
  projectMatchJobsResultData,
  type CompactMatchJobsResult,
} from '../features/jobs/matchResult';
import type {StreamCallbacks} from '../lib/api/chat';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const EVENT_A = '11111111-1111-4111-8111-111111111111';
const EVENT_B = '22222222-2222-4222-8222-222222222222';
const EVENT_C = '33333333-3333-4333-8333-333333333333';
const EVENT_D = '44444444-4444-4444-8444-444444444444';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const JOB_HIGH = 'job-high';
const JOB_LOW = 'job-low';
const TS = '2026-07-15T12:00:00.000Z';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function skillEvidenceDirect(): JsonObject {
  return {
    job_skill_key: 'python',
    job_skill_display_name: 'Python',
    match_type: 'direct',
    strength: 1.0,
    candidate_skill_key: 'python',
    candidate_skill_display_name: 'Python',
    job_evidence: ['Python 3'],
    candidate_evidence: ['Python expert'],
    relationship_from_key: null,
    relationship_to_key: null,
    relationship_weight: null,
    relationship_source: null,
  };
}

function skillEvidenceRelated(): JsonObject {
  return {
    job_skill_key: 'typescript',
    job_skill_display_name: 'TypeScript',
    match_type: 'related',
    strength: 0.6,
    candidate_skill_key: 'javascript',
    candidate_skill_display_name: 'JavaScript',
    job_evidence: ['TypeScript'],
    candidate_evidence: ['JS'],
    relationship_from_key: 'javascript',
    relationship_to_key: 'typescript',
    relationship_weight: 0.7,
    relationship_source: 'skills_seed.yaml',
  };
}

function missingSkill(): JsonObject {
  return {
    job_skill_key: 'kubernetes',
    job_skill_display_name: 'Kubernetes',
    job_evidence: ['k8s required'],
  };
}

function matchResultHigh(overrides?: JsonObject): JsonObject {
  return {
    job_id: JOB_HIGH,
    title: 'Senior Backend Engineer',
    company: 'Acme Corp',
    location: 'Berlin',
    work_mode: 'remote',
    source_url: 'https://example.com/jobs/1',
    final_score: 0.8123456789,
    quality_multiplier: 1.0,
    components: {
      semantic_similarity: 0.9,
      skill_score: 0.8,
      seniority_score: 1.0,
      experience_score: 0.75,
      location_score: null,
      work_mode_score: 1.0,
    },
    effective_weights: {
      semantic_similarity: 0.3157894736842105,
      skill_score: 0.42105263157894735,
      seniority_score: 0.10526315789473684,
      experience_score: 0.10526315789473684,
      work_mode_score: 0.05263157894736842,
    },
    matched_required_skills: [skillEvidenceDirect()],
    matched_preferred_skills: [],
    related_skills: [skillEvidenceRelated()],
    missing_required_skills: [missingSkill()],
    summary: 'Strong match on Python; missing Kubernetes.',
    ...overrides,
  };
}

function matchResultLow(overrides?: JsonObject): JsonObject {
  return {
    job_id: JOB_LOW,
    title: 'Frontend Dev',
    company: 'Beta Inc',
    location: null,
    work_mode: 'hybrid',
    source_url: null,
    final_score: 0.401234,
    quality_multiplier: 0.85,
    components: {
      semantic_similarity: 0.5,
      skill_score: null,
      seniority_score: null,
      experience_score: null,
      location_score: null,
      work_mode_score: 0.5,
    },
    effective_weights: {
      semantic_similarity: 0.8571428571428571,
      work_mode_score: 0.14285714285714285,
    },
    matched_required_skills: [],
    matched_preferred_skills: [],
    related_skills: [],
    missing_required_skills: [],
    summary: 'Partial quality; limited components available.',
    ...overrides,
  };
}

/** Backend-authoritative match_jobs ToolResult.data fixture. */
function compactMatchData(
  results: JsonObject[] = [matchResultHigh(), matchResultLow()],
  limit = 10,
): JsonObject {
  return {
    results,
    count: results.length,
    limit,
  };
}

function toolExecution(
  resultData: JsonObject | null,
  overrides?: Partial<Omit<ToolExecutionView, 'result'>> & {
    result?: ToolResult;
  },
): ToolExecutionView {
  const result: ToolResult =
    overrides?.result ??
    ({
      ok: true,
      code: null,
      summary: 'Matched 2 job(s)',
      data: resultData,
    } satisfies ToolResult);
  return {
    id: TOOL_EXEC,
    tool_call_id: 'tc-match-1',
    tool_name: 'match_jobs',
    status: 'completed',
    duration_ms: 200,
    error_code: null,
    arguments_summary: null,
    created_at: TS,
    updated_at: TS,
    ...overrides,
    result,
  };
}

function historyWithMatchJobs(
  data: JsonObject | null = compactMatchData(),
  toolOverrides?: Parameters<typeof toolExecution>[1],
): HistoryPage {
  const tool = toolExecution(data, toolOverrides);
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content: 'Match me to jobs',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: {
          id: RUN_ID,
          user_message_id: MSG_USER,
          state: 'completed',
          pending_approval: null,
          error_code: null,
          completed_at: TS,
          created_at: TS,
          updated_at: TS,
          tool_executions: [tool],
        },
      },
      {
        id: MSG_ASST,
        role: 'assistant',
        content: 'Here are your top matches.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function renderWithTheme(ui: ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

function renderChat(deps: ChatPageDeps) {
  return renderWithTheme(<ChatPage deps={deps} />);
}

function sse(
  eventId: string,
  event: SseEvent['event'],
  payload: Record<string, unknown>,
): SseEvent {
  return parseSseEventData({
    event_id: eventId,
    run_id: RUN_ID,
    timestamp: TS,
    event,
    payload,
  });
}

/** Count assistant rows that would host match cards. */
function matchCardHostCount(
  messages: ReturnType<typeof createInitialChatState>['messages'],
): number {
  let count = 0;
  for (let i = 0; i < messages.length; i += 1) {
    if (messages[i].role !== 'assistant') {
      continue;
    }
    const tools = toolsForAssistantDisplay(messages, i);
    if (matchJobsResultForTools(tools) !== null) {
      count += 1;
    }
  }
  return count;
}

describe('strict compact match_jobs parsing', () => {
  it('parses ordered results with unavailable components and skill groups', () => {
    const parsed = parseMatchJobsResultData(compactMatchData());
    expect(parsed).not.toBeNull();
    expect(parsed!.count).toBe(2);
    expect(parsed!.limit).toBe(10);
    expect(parsed!.results.map((r) => r.jobId)).toEqual([JOB_HIGH, JOB_LOW]);
    expect(parsed!.results[0].sourceUrl).toBe('https://example.com/jobs/1');
    expect(parsed!.results[0].components.locationScore).toBeNull();
    expect(parsed!.results[0].matchedRequiredSkills[0].jobSkillDisplayName).toBe(
      'Python',
    );
    expect(parsed!.results[0].relatedSkills[0].matchType).toBe('related');
    expect(parsed!.results[0].missingRequiredSkills[0].jobSkillKey).toBe(
      'kubernetes',
    );
    expect(parsed!.results[1].sourceUrl).toBeNull();
    expect(parsed!.results[1].components.skillScore).toBeNull();
    expect(parsed!.results[1].qualityMultiplier).toBe(0.85);
    expect(parsed!.results[0].effectiveWeights.map((w) => w.key)).toEqual([
      'semantic_similarity',
      'skill_score',
      'seniority_score',
      'experience_score',
      'work_mode_score',
    ]);
  });

  it('rejects missing fields, invalid work_mode, extra keys, and count mismatch', () => {
    expect(parseMatchJobsResultData(null)).toBeNull();
    expect(parseMatchJobsResultData({results: [], count: 0})).toBeNull();
    expect(
      parseMatchJobsResultData(
        compactMatchData([
          matchResultHigh({work_mode: 'anywhere'}),
        ]),
      ),
    ).toBeNull();
    expect(
      parseMatchJobsResultData({
        ...compactMatchData(),
        raw_content: 'secret',
      }),
    ).toBeNull();
    expect(
      parseMatchJobsResultData({
        results: [matchResultHigh()],
        count: 2,
        limit: 10,
      }),
    ).toBeNull();
    expect(
      parseMatchJobsResultData({
        results: [matchResultHigh()],
        count: 1,
        limit: 11,
      }),
    ).toBeNull();
  });

  it('rejects more than 10 results and adversarial keys', () => {
    const eleven = Array.from({length: 11}, (_, i) =>
      matchResultHigh({job_id: `job-${i}`, title: `Role ${i}`}),
    );
    expect(parseMatchJobsResultData(compactMatchData(eleven))).toBeNull();
    expect(
      parseMatchJobsResultData({
        ...compactMatchData(),
        embedding_json: '[]',
        storage_path: '/secret',
      }),
    ).toBeNull();
    expect(
      parseMatchJobsResultData(
        compactMatchData([
          matchResultHigh({
            matched_required_skills: [
              {
                ...skillEvidenceDirect(),
                match_type: 'direct',
                relationship_from_key: 'python',
              },
            ],
          }),
        ]),
      ),
    ).toBeNull();
  });

  it('allowlist projection retains only match_jobs keys and rejects other tools', () => {
    const projected = projectMatchJobsResultData('match_jobs', {
      ...compactMatchData(),
      raw_content: 'FULL JD',
      embedding_json: '[]',
      storage_path: '/data',
      api_key: 'sk-test',
    });
    expect(projected).not.toBeNull();
    expect(projected).not.toHaveProperty('raw_content');
    expect(projected).not.toHaveProperty('embedding_json');
    expect(projected).not.toHaveProperty('storage_path');
    expect(projected).not.toHaveProperty('api_key');
    expect(parseMatchJobsResultData(projected)?.results[0].jobId).toBe(
      JOB_HIGH,
    );
    expect(
      projectMatchJobsResultData('save_job', compactMatchData()),
    ).toBeNull();
    expect(
      projectMatchJobsResultData('query_jobs', compactMatchData()),
    ).toBeNull();
  });

  it('formats display score without mutating source value', () => {
    const raw = 0.8123456789;
    expect(formatDisplayScore(raw)).toBe('81.2%');
    expect(raw).toBe(0.8123456789);
  });

  it('accepts only safe http(s) source URLs on parse', () => {
    const safe = parseMatchJobsResultData(
      compactMatchData([
        matchResultHigh({source_url: 'https://example.com/j'}),
      ]),
    );
    expect(safe!.results[0].sourceUrl).toBe('https://example.com/j');
    const bad = parseMatchJobsResultData(
      compactMatchData([
        matchResultHigh({source_url: 'javascript:alert(1)'}),
      ]),
    );
    expect(bad!.results[0].sourceUrl).toBeNull();
  });
});

describe('MatchCard rendering', () => {
  it('surfaces the final score and decisive components in a compact summary', () => {
    const parsed = parseMatchJobsResultData(
      compactMatchData([matchResultHigh()]),
    )!;

    renderWithTheme(<MatchCard data={parsed.results[0]} />);

    const summary = screen.getByTestId('jobagent-match-score-summary');
    expect(summary).toHaveTextContent('81.2%');
    expect(summary).toHaveTextContent('Độ tương đồng');
    expect(summary).toHaveTextContent('90.0%');
    expect(summary).toHaveTextContent('Độ phủ kỹ năng');
    expect(summary).toHaveTextContent('80.0%');
    expect(summary).toHaveTextContent('Hệ số chất lượng');
    expect(summary).toHaveTextContent('1.00');
  });

  it('renders title, company, location, work mode, rounded score, skills, and source', async () => {
    const parsed = parseMatchJobsResultData(
      compactMatchData([matchResultHigh()]),
    )!;
    renderWithTheme(<MatchCard data={parsed.results[0]} />);
    expect(screen.getByTestId('jobagent-match-card')).toBeInTheDocument();
    expect(
      screen.getAllByText('Senior Backend Engineer').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Berlin')).toBeInTheDocument();
    expect(screen.getByText('Từ xa')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-match-final-score')).toHaveTextContent(
      '81.2%',
    );
    expect(
      within(screen.getByTestId('jobagent-match-matched-required')).getByText(
        'Python',
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('jobagent-match-related-skills')).getByText(
        'TypeScript',
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('jobagent-match-missing-required')).getByText(
        'Kubernetes',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Kỹ năng đã khớp')).toBeInTheDocument();
    expect(screen.getByText('Kỹ năng liên quan')).toBeInTheDocument();
    expect(screen.getByText('Kỹ năng còn thiếu')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /example.com/})).toHaveAttribute(
      'href',
      'https://example.com/jobs/1',
    );
    // Score renders as rounded percentage text; skills via Token labels only.
    expect(screen.getByTestId('jobagent-match-final-score').tagName).toBe(
      'SPAN',
    );
  });

  it('omits null location/source and shows unavailable components with weights', async () => {
    const parsed = parseMatchJobsResultData(
      compactMatchData([matchResultLow()]),
    )!;
    const user = userEvent.setup();
    renderWithTheme(<MatchCard data={parsed.results[0]} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByTestId('jobagent-match-final-score')).toHaveTextContent(
      '40.1%',
    );

    // Expand collapsible score breakdown.
    const trigger = screen.getByText('Chi tiết cách tính điểm');
    await user.click(trigger);

    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-match-component-location_score'),
      ).toHaveAttribute('data-available', 'false');
    });
    expect(
      screen.getByTestId('jobagent-match-component-skill_score'),
    ).toHaveAttribute('data-available', 'false');
    expect(screen.getAllByText('Không có dữ liệu').length).toBeGreaterThanOrEqual(1);
    const breakdown = screen.getByTestId('jobagent-match-score-breakdown');
    expect(within(breakdown).getByText(/Hệ số chất lượng/i)).toBeInTheDocument();
    expect(within(breakdown).getByText('0.85')).toBeInTheDocument();
    // Effective weights present for available components.
    expect(screen.getAllByText(/Trọng số thực tế:/i).length).toBeGreaterThanOrEqual(
      1,
    );
  });

  it('shows high-result unavailable location and effective weights when expanded', async () => {
    const parsed = parseMatchJobsResultData(
      compactMatchData([matchResultHigh()]),
    )!;
    const user = userEvent.setup();
    renderWithTheme(<MatchCard data={parsed.results[0]} />);
    await user.click(screen.getByText('Chi tiết cách tính điểm'));
    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-match-component-location_score'),
      ).toHaveTextContent('Không có dữ liệu');
    });
    expect(
      screen.getByTestId('jobagent-match-component-semantic_similarity'),
    ).toHaveAttribute('data-available', 'true');
    expect(
      within(screen.getByTestId('jobagent-match-score-breakdown')).getByText(
        '1.00',
      ),
    ).toBeInTheDocument();
  });
});

describe('history resultData + friendly Match Jobs label', () => {
  it('toolViewToActivity projects allowlisted match_jobs data and drops adversarial keys', () => {
    const activity = toolViewToActivity(
      toolExecution({
        ...compactMatchData(),
        raw_content: 'SECRET',
        embedding_json: '[]',
        storage_path: '/data',
        api_key: 'sk-live',
      }),
    );
    expect(activity.source).toBe('history');
    expect(activity.resultData).not.toBeNull();
    expect(activity.resultData).not.toHaveProperty('raw_content');
    expect(activity.resultData).not.toHaveProperty('embedding_json');
    expect(activity.resultData).not.toHaveProperty('storage_path');
    expect(activity.resultData).not.toHaveProperty('api_key');
    const parsed = parseMatchJobsResultData(activity.resultData);
    expect(parsed?.results.map((r) => r.jobId)).toEqual([JOB_HIGH, JOB_LOW]);
  });

  it('stream tool_status keeps resultData null until rehydrate', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'match_jobs',
        status: 'running',
        duration_ms: null,
        summary: 'Matching…',
        error_code: null,
      }),
    });
    const tools = state.messages.find((m) => m.role === 'assistant')?.run?.tools;
    expect(tools?.[0].resultData).toBeNull();
    expect(tools?.[0].status).toBe('running');
  });

  it('history/rehydrate replaces stream tools with durable ordered match data', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'match_jobs',
        status: 'running',
        duration_ms: null,
        summary: null,
        error_code: null,
      }),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_C, 'run_completed', {state: 'completed'}),
    });

    const page = historyWithMatchJobs();
    const {messages} = rehydrateWithDurableTruth(state.messages, page);
    const userTools = messages.find((m) => m.id === MSG_USER)?.run?.tools;
    expect(userTools?.[0].source).toBe('history');
    expect(userTools?.[0].status).toBe('completed');
    const parsed = parseMatchJobsResultData(userTools?.[0].resultData ?? null);
    expect(parsed?.results.map((r) => r.jobId)).toEqual([JOB_HIGH, JOB_LOW]);
    expect(messages.some((m) => m.id === `assistant:${RUN_ID}`)).toBe(false);
    expect(matchCardHostCount(messages)).toBe(1);
  });

  it('restart hydration via history/reset preserves backend order', () => {
    const {messages} = hydrateFromHistoryPage(historyWithMatchJobs());
    const tools = messages[0].run?.tools ?? [];
    const parsed = parseMatchJobsResultData(tools[0].resultData);
    expect(parsed?.results.map((r) => r.jobId)).toEqual([JOB_HIGH, JOB_LOW]);
    const state = chatReducer(createInitialChatState(), {
      type: 'history/reset',
      page: historyWithMatchJobs(),
    });
    expect(matchCardHostCount(state.messages)).toBe(1);
    const hostTools = toolsForAssistantDisplay(state.messages, 1);
    const hostParsed = matchJobsResultForTools(hostTools);
    expect(hostParsed?.results.map((r) => r.jobId)).toEqual([
      JOB_HIGH,
      JOB_LOW,
    ]);
  });

  it('uses friendly Match Jobs label', () => {
    expect(friendlyToolLabel('match_jobs')).toBe('Match Jobs');
    expect(friendlyToolLabel('save_job')).toBe('Save Job');
  });
});

describe('ChatPage durable match cards', () => {
  it('renders ordered cards from restart history load exactly once', async () => {
    const loadHistory = vi.fn().mockResolvedValue(historyWithMatchJobs());
    renderChat({loadHistory, sendTurn: vi.fn()});

    await waitFor(() => {
      expect(screen.getAllByTestId('jobagent-match-card')).toHaveLength(2);
    });
    const cards = screen.getAllByTestId('jobagent-match-card');
    expect(cards[0]).toHaveAttribute('data-job-id', JOB_HIGH);
    expect(cards[1]).toHaveAttribute('data-job-id', JOB_LOW);
    expect(screen.getByText('Match Jobs')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('81.2%')).toBeInTheDocument();
    expect(screen.getByText('40.1%')).toBeInTheDocument();
    expect(screen.queryByText(/raw_content|embedding_json/i)).not.toBeInTheDocument();
  });

  it('terminal rehydrate renders exactly one host with backend order', () => {
    let state = createInitialChatState();
    state = chatReducer(state, {
      type: 'turn/start',
      clientKey: 'user:live',
      message: 'Match me',
      createdAt: '2026-07-15T11:00:00.000Z',
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_B, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'match_jobs',
        status: 'running',
        duration_ms: null,
        summary: 'Matching…',
        error_code: null,
      }),
    });
    expect(
      state.messages.find((m) => m.role === 'assistant')?.run?.tools?.[0]
        .resultData,
    ).toBeNull();

    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_C, 'tool_status', {
        tool_execution_id: TOOL_EXEC,
        tool_call_id: 'tc1',
        tool_name: 'match_jobs',
        status: 'completed',
        duration_ms: 80,
        summary: 'Matched',
        error_code: null,
      }),
    });
    state = chatReducer(state, {
      type: 'sse/event',
      event: sse(EVENT_D, 'run_completed', {state: 'completed'}),
    });

    state = chatReducer(state, {
      type: 'history/rehydrate',
      page: historyWithMatchJobs(),
    });

    expect(matchCardHostCount(state.messages)).toBe(1);
    expect(state.messages.some((m) => m.id === `assistant:${RUN_ID}`)).toBe(
      false,
    );

    renderWithTheme(
      <ChatMessages
        messages={state.messages}
        streamPhase="idle"
        streamError={null}
        assistantStatus={null}
        isStreaming={false}
      />,
    );
    const cards = screen.getAllByTestId('jobagent-match-card');
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute('data-job-id', JOB_HIGH);
    expect(cards[1]).toHaveAttribute('data-job-id', JOB_LOW);
  });

  it('ChatPage invokes history rehydrate after terminal run_completed with exact cards', async () => {
    const durablePage = historyWithMatchJobs();
    let historyCalls = 0;
    const loadHistory = vi.fn(async () => {
      historyCalls += 1;
      if (historyCalls === 1) {
        return {items: [], next_cursor: null};
      }
      return durablePage;
    });
    const sendTurn = vi.fn(
      async (
        _body: {message: string},
        cbs: StreamCallbacks,
        _signal?: AbortSignal,
      ) => {
        cbs.onEvent(
          sse(EVENT_A, 'run_started', {state: 'running', resumed: false}),
        );
        cbs.onEvent(
          sse(EVENT_C, 'tool_status', {
            tool_execution_id: TOOL_EXEC,
            tool_call_id: 'tc1',
            tool_name: 'match_jobs',
            status: 'completed',
            duration_ms: 50,
            summary: 'Matched',
            error_code: null,
          }),
        );
        cbs.onEvent(sse(EVENT_D, 'run_completed', {state: 'completed'}));
      },
    );

    const {container} = renderChat({loadHistory, sendTurn});
    await waitFor(() => {
      expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    });
    const user = userEvent.setup();
    const editable =
      (container.querySelector(
        '[contenteditable="true"]',
      ) as HTMLElement | null) ??
      (container.querySelector('[role="textbox"]') as HTMLElement | null);
    await user.click(editable!);
    await user.keyboard('Please match me to jobs');
    await waitFor(() => {
      expect(
        screen
          .getAllByRole('button', {name: 'Send'})
          .some((b) => !(b as HTMLButtonElement).disabled),
      ).toBe(true);
    });
    await user.click(
      screen
        .getAllByRole('button', {name: 'Send'})
        .find((b) => !(b as HTMLButtonElement).disabled)!,
    );
    await waitFor(() => {
      expect(historyCalls).toBeGreaterThanOrEqual(2);
    });
    await waitFor(() => {
      expect(screen.getAllByTestId('jobagent-match-card')).toHaveLength(2);
    });
    const cards = screen.getAllByTestId('jobagent-match-card');
    expect(cards[0]).toHaveAttribute('data-job-id', JOB_HIGH);
    expect(cards[1]).toHaveAttribute('data-job-id', JOB_LOW);
  });

  it('preserves at most 10 ordered cards and never re-sorts', async () => {
    const ten = Array.from({length: 10}, (_, i) =>
      matchResultLow({
        job_id: `job-ord-${i}`,
        title: `Role ${i}`,
        // Descending scores in array so a sort by score would reverse.
        final_score: 0.1 + i * 0.01,
      }),
    );
    const page = historyWithMatchJobs(compactMatchData(ten));
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(page),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getAllByTestId('jobagent-match-card')).toHaveLength(10);
    });
    const cards = screen.getAllByTestId('jobagent-match-card');
    for (let i = 0; i < 10; i += 1) {
      expect(cards[i]).toHaveAttribute('data-job-id', `job-ord-${i}`);
    }
  });
});

// Type-only guard that CompactMatchJobsResult remains the host projection type.
void (0 as unknown as CompactMatchJobsResult | null);

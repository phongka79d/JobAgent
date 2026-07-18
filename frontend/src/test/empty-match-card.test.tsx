/**
 * Zero-result match_jobs recovery card tests (Plan 10 Batch07 07A).
 * Exact Vietnamese copy, zero-only gating, durable source_message_id,
 * pending dedup, created/reused/unavailable/error, MatchCard reuse, invalidation.
 */
import type {ReactElement} from 'react';
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {renderHook} from '@testing-library/react';

import {App} from '../app/App';
import {ChatPage, type ChatPageDeps} from '../features/chat/ChatPage';
import {
  EMPTY_MATCH_CTA,
  EMPTY_MATCH_EXPLANATION,
  EMPTY_MATCH_HEADING,
  EMPTY_MATCH_UNAVAILABLE_HINT,
  EmptyMatchResultCard,
} from '../features/chat/components/EmptyMatchResultCard';
import {
  isZeroResultMatchJobs,
  sourceMessageIdForAssistantDisplay,
  toolsForAssistantDisplay,
} from '../features/chat/components/ChatMessageRow';
import {hydrateFromHistoryPage} from '../features/chat/history';
import {
  chatReducer,
  createInitialChatState,
  type ClientToolActivity,
} from '../features/chat/reducer';
import type {
  HistoryPage,
  JsonObject,
  ToolExecutionView,
  ToolResult,
} from '../features/chat/types';
import {useSavedJobRecovery} from '../features/chat/useSavedJobRecovery';
import type {SaveAndEvaluateResponse} from '../features/jobs/types';

const RUN_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const TOOL_EXEC = '77777777-7777-4777-8777-777777777777';
const MSG_USER = '88888888-8888-4888-8888-888888888888';
const MSG_ASST = '99999999-9999-4999-8999-999999999999';
const MSG_USER_B = 'aaaa1111-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const MSG_ASST_B = 'bbbb2222-cccc-4ddd-8eee-ffffffffffff';
const JOB_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const EVAL_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';
const TS = '2026-07-18T12:00:00.000Z';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderWithTheme(ui: ReactElement) {
  return render(<Theme theme={neutralTheme}>{ui}</Theme>);
}

function matchResultPayload(jobId: string, score = 0.81): JsonObject {
  return {
    job_id: jobId,
    title: 'Backend Engineer',
    company: 'Acme',
    location: 'Berlin',
    work_mode: 'hybrid',
    source_url: null,
    final_score: score,
    quality_multiplier: 1.0,
    components: {
      semantic_similarity: score,
      skill_score: null,
      seniority_score: null,
      experience_score: null,
      location_score: null,
      work_mode_score: null,
    },
    effective_weights: {semantic_similarity: 1.0},
    matched_required_skills: [],
    matched_preferred_skills: [],
    related_skills: [],
    missing_required_skills: [],
    summary: 'Solid fit',
  };
}

function zeroMatchData(limit = 10): JsonObject {
  return {results: [], count: 0, limit};
}

function nonzeroMatchData(): JsonObject {
  return {
    results: [matchResultPayload(JOB_ID)],
    count: 1,
    limit: 10,
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
      summary: 'Matched 0 job(s)',
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

function historyWithZeroMatch(
  data: JsonObject | null = zeroMatchData(),
  toolOverrides?: Parameters<typeof toolExecution>[1],
  content = 'Please match https://example.com/jd',
): HistoryPage {
  const tool = toolExecution(data, toolOverrides);
  return {
    items: [
      {
        id: MSG_USER,
        role: 'user',
        content,
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
        content: 'No ranked matches yet.',
        structured_payload: null,
        created_at: TS,
        updated_at: TS,
        run: null,
      },
    ],
    next_cursor: null,
  };
}

function listItemPayload(id: string) {
  return {
    id,
    title: 'Backend Engineer',
    company: 'Acme',
    processing_status: 'processed' as const,
    jd_quality: 'full' as const,
    source_type: 'text' as const,
    source_url: null,
    created_at: TS,
    updated_at: TS,
    evaluation_state: 'current' as const,
    latest_score: 0.81,
  };
}

function saveSuccessResponse(
  outcome: 'created' | 'reused' = 'created',
): SaveAndEvaluateResponse {
  return {
    ingest_outcome: outcome === 'created' ? 'created' : 'existing',
    job: listItemPayload(JOB_ID),
    evaluation_outcome: outcome,
    evaluation: {
      id: EVAL_ID,
      job_id: JOB_ID,
      evaluation_state: 'current',
      evaluation_context_hash: 'ctx-hash',
      result: {
        jobId: JOB_ID,
        title: 'Backend Engineer',
        company: 'Acme',
        location: 'Berlin',
        workMode: 'hybrid',
        sourceUrl: null,
        finalScore: 0.81,
        qualityMultiplier: 1,
        components: {
          semanticSimilarity: 0.81,
          skillScore: null,
          seniorityScore: null,
          experienceScore: null,
          locationScore: null,
          workModeScore: null,
        },
        effectiveWeights: [{key: 'semantic_similarity', weight: 1}],
        matchedRequiredSkills: [],
        matchedPreferredSkills: [],
        relatedSkills: [],
        missingRequiredSkills: [],
        summary: 'Solid fit',
      },
      created_at: TS,
      updated_at: TS,
    },
    code: null,
  };
}

function saveUnavailableResponse(): SaveAndEvaluateResponse {
  return {
    ingest_outcome: 'created',
    job: {
      ...listItemPayload(JOB_ID),
      evaluation_state: 'none',
      latest_score: null,
      jd_quality: 'unscorable',
    },
    evaluation_outcome: 'unavailable',
    evaluation: null,
    code: 'JOB_NOT_SCORABLE',
  };
}

function renderChat(deps: ChatPageDeps) {
  return renderWithTheme(<ChatPage deps={deps} />);
}

function activityFromHistory(
  page: HistoryPage,
): {
  tools: readonly ClientToolActivity[];
  sourceId: string | null;
  messages: ReturnType<typeof createInitialChatState>['messages'];
} {
  let state = createInitialChatState();
  state = chatReducer(state, {type: 'history/reset', page});
  const messages = state.messages;
  let tools: readonly ClientToolActivity[] = [];
  let sourceId: string | null = null;
  for (let i = 0; i < messages.length; i += 1) {
    if (messages[i].role !== 'assistant') {
      continue;
    }
    tools = toolsForAssistantDisplay(messages, i);
    sourceId = sourceMessageIdForAssistantDisplay(messages, i);
    break;
  }
  return {tools, sourceId, messages};
}

describe('EmptyMatchResultCard copy and presentation', () => {
  it('renders exact Vietnamese heading, CTA, and one short explanation', () => {
    const onSave = vi.fn();
    renderWithTheme(
      <EmptyMatchResultCard
        sourceMessageId={MSG_USER}
        isPending={false}
        recoveredMatch={null}
        failureHint={null}
        onSaveAndEvaluate={onSave}
      />,
    );
    expect(screen.getByTestId('jobagent-empty-match-card')).toHaveAttribute(
      'data-source-message-id',
      MSG_USER,
    );
    expect(screen.getByText(EMPTY_MATCH_HEADING)).toBeInTheDocument();
    expect(screen.getByText(EMPTY_MATCH_EXPLANATION)).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: EMPTY_MATCH_CTA}),
    ).toBeInTheDocument();
    expect(EMPTY_MATCH_HEADING).toBe('Chưa có kết quả đánh giá');
    expect(EMPTY_MATCH_CTA).toBe('Lưu JD & đánh giá lại');
  });

  it('disables CTA while pending and invokes durable source id only', async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    const {rerender} = renderWithTheme(
      <EmptyMatchResultCard
        sourceMessageId={MSG_USER}
        isPending={false}
        recoveredMatch={null}
        failureHint={null}
        onSaveAndEvaluate={onSave}
      />,
    );
    await user.click(screen.getByTestId('jobagent-empty-match-cta'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(MSG_USER);

    rerender(
      <Theme theme={neutralTheme}>
        <EmptyMatchResultCard
          sourceMessageId={MSG_USER}
          isPending
          recoveredMatch={null}
          failureHint={null}
          onSaveAndEvaluate={onSave}
        />
      </Theme>,
    );
    expect(screen.getByTestId('jobagent-empty-match-cta')).toBeDisabled();
  });

  it('replaces empty card with MatchCard on recovered match', () => {
    const recovered = saveSuccessResponse().evaluation!.result;
    renderWithTheme(
      <EmptyMatchResultCard
        sourceMessageId={MSG_USER}
        isPending={false}
        recoveredMatch={recovered}
        failureHint={null}
        onSaveAndEvaluate={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('jobagent-empty-match-card')).toBeNull();
    expect(screen.getByTestId('jobagent-match-card')).toHaveAttribute(
      'data-job-id',
      JOB_ID,
    );
    expect(screen.getByTestId('jobagent-empty-match-recovered')).toHaveAttribute(
      'data-source-message-id',
      MSG_USER,
    );
  });
});

describe('zero-only gate and durable source binding', () => {
  it('parses successful count=0 and binds initiating user message id', () => {
    const page = historyWithZeroMatch();
    const {tools, sourceId, messages} = activityFromHistory(page);
    expect(isZeroResultMatchJobs(tools)).toBe(true);
    expect(sourceId).toBe(MSG_USER);
    // Never the assistant message id.
    expect(sourceId).not.toBe(MSG_ASST);
    expect(messages.find((m) => m.id === MSG_USER)?.content).toContain(
      'Please match',
    );
  });

  it('never qualifies failed, malformed, non-match_jobs, or nonzero payloads', () => {
    const failed = activityFromHistory(
      historyWithZeroMatch(zeroMatchData(), {
        status: 'failed',
        error_code: 'NEO4J_UNAVAILABLE',
        result: {
          ok: false,
          code: 'NEO4J_UNAVAILABLE',
          summary: 'Graph unavailable',
          data: zeroMatchData(),
        },
      }),
    );
    expect(isZeroResultMatchJobs(failed.tools)).toBe(false);

    const malformed = activityFromHistory(
      historyWithZeroMatch({results: [], count: 0} as JsonObject),
    );
    // Missing limit → strict parse fails → no CTA.
    expect(isZeroResultMatchJobs(malformed.tools)).toBe(false);

    const wrongToolPage: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'query',
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
            tool_executions: [
              toolExecution(zeroMatchData(), {tool_name: 'query_jobs'}),
            ],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'ok',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    expect(isZeroResultMatchJobs(activityFromHistory(wrongToolPage).tools)).toBe(
      false,
    );

    const nonzero = activityFromHistory(historyWithZeroMatch(nonzeroMatchData()));
    expect(isZeroResultMatchJobs(nonzero.tools)).toBe(false);
  });

  it('ChatPage shows one recovery card for durable zero-result history only', async () => {
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(historyWithZeroMatch()),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-empty-match-card')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('jobagent-empty-match-card')).toHaveLength(1);
    expect(screen.getByText(EMPTY_MATCH_HEADING)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: EMPTY_MATCH_CTA})).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-match-card')).toBeNull();
  });

  it('ChatPage never shows recovery CTA for nonzero match_jobs', async () => {
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(historyWithZeroMatch(nonzeroMatchData())),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-match-card')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('jobagent-empty-match-card')).toBeNull();
    expect(screen.queryByRole('button', {name: EMPTY_MATCH_CTA})).toBeNull();
  });

  it('ChatPage never shows recovery CTA for failed match_jobs', async () => {
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(
        historyWithZeroMatch(zeroMatchData(), {
          status: 'failed',
          error_code: 'NEO4J_REBUILD_REQUIRED',
          result: {
            ok: false,
            code: 'NEO4J_REBUILD_REQUIRED',
            summary: 'Rebuild required',
            data: zeroMatchData(),
          },
        }),
      ),
      sendTurn: vi.fn(),
    });
    await waitFor(() => {
      expect(screen.getByText('No ranked matches yet.')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('jobagent-empty-match-card')).toBeNull();
    expect(screen.queryByRole('button', {name: EMPTY_MATCH_CTA})).toBeNull();
  });
});

describe('useSavedJobRecovery lifecycle', () => {
  it('dedupes pending recover and maps created success to MatchResult', async () => {
    let resolve!: (v: SaveAndEvaluateResponse) => void;
    const pending = new Promise<SaveAndEvaluateResponse>((r) => {
      resolve = r;
    });
    const saveAndEvaluateJob = vi.fn().mockReturnValue(pending);
    const onInvalidated = vi.fn();
    const {result} = renderHook(() =>
      useSavedJobRecovery({
        api: {saveAndEvaluateJob},
        onInvalidated,
      }),
    );

    let first!: Promise<string>;
    let second!: Promise<string>;
    act(() => {
      first = result.current.recover(MSG_USER);
      second = result.current.recover(MSG_USER);
    });
    expect(await second).toBe('duplicate');
    expect(result.current.isPending(MSG_USER)).toBe(true);

    await act(async () => {
      resolve(saveSuccessResponse('created'));
      await first;
    });
    expect(await first).toBe('success');
    expect(saveAndEvaluateJob).toHaveBeenCalledTimes(1);
    expect(saveAndEvaluateJob).toHaveBeenCalledWith(MSG_USER, undefined);
    expect(result.current.getEntry(MSG_USER).phase).toBe('success');
    expect(result.current.getEntry(MSG_USER).recoveredMatch?.jobId).toBe(JOB_ID);
    expect(onInvalidated).toHaveBeenCalledTimes(1);
  });

  it('keeps recovery UI on unavailable and error without success claim', async () => {
    const saveUnavailable = vi.fn().mockResolvedValue(saveUnavailableResponse());
    const {result, rerender} = renderHook(
      ({api}: {api: {saveAndEvaluateJob: typeof saveUnavailable}}) =>
        useSavedJobRecovery({api}),
      {initialProps: {api: {saveAndEvaluateJob: saveUnavailable}}},
    );
    await act(async () => {
      await result.current.recover(MSG_USER);
    });
    expect(result.current.getEntry(MSG_USER).phase).toBe('unavailable');
    expect(result.current.getEntry(MSG_USER).recoveredMatch).toBeNull();
    expect(result.current.getEntry(MSG_USER).failureHint).toBe(
      EMPTY_MATCH_UNAVAILABLE_HINT,
    );

    const saveError = vi.fn().mockRejectedValue({
      code: 'JD_SOURCE_NOT_RECOVERABLE',
      summary: 'Source not recoverable',
    });
    rerender({api: {saveAndEvaluateJob: saveError}});
    await act(async () => {
      await result.current.recover(MSG_USER_B);
    });
    expect(result.current.getEntry(MSG_USER_B).phase).toBe('error');
    expect(result.current.getEntry(MSG_USER_B).recoveredMatch).toBeNull();
    expect(result.current.getEntry(MSG_USER_B).failureHint).toContain(
      'Source not recoverable',
    );
  });
});

describe('ChatPage recovery action wiring', () => {
  it('submits only durable source_message_id and shows MatchCard on success', async () => {
    const saveAndEvaluateJob = vi
      .fn()
      .mockResolvedValue(saveSuccessResponse('reused'));
    const onInvalidated = vi.fn();
    const user = userEvent.setup();
    renderWithTheme(
      <ChatPage
        deps={{
          loadHistory: vi.fn().mockResolvedValue(historyWithZeroMatch()),
          sendTurn: vi.fn(),
          saveAndEvaluateJob,
        }}
        onSavedJobsInvalidated={onInvalidated}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-empty-match-cta')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('jobagent-empty-match-cta'));
    await waitFor(() => {
      expect(saveAndEvaluateJob).toHaveBeenCalledWith(MSG_USER, undefined);
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-match-card')).toHaveAttribute(
        'data-job-id',
        JOB_ID,
      );
    });
    expect(screen.queryByTestId('jobagent-empty-match-card')).toBeNull();
    expect(onInvalidated).toHaveBeenCalled();
  });

  it('keeps recovery card and failure hint on unavailable', async () => {
    const saveAndEvaluateJob = vi
      .fn()
      .mockResolvedValue(saveUnavailableResponse());
    const user = userEvent.setup();
    renderChat({
      loadHistory: vi.fn().mockResolvedValue(historyWithZeroMatch()),
      sendTurn: vi.fn(),
      saveAndEvaluateJob,
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-empty-match-cta')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('jobagent-empty-match-cta'));
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-empty-match-failure')).toBeInTheDocument();
    });
    expect(screen.getByText(EMPTY_MATCH_UNAVAILABLE_HINT)).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-empty-match-card')).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-match-card')).toBeNull();
  });

  it('App invalidation remounts saved-JD sidebar cache key path', async () => {
    const saveAndEvaluateJob = vi
      .fn()
      .mockResolvedValue(saveSuccessResponse('created'));
    const loadHistory = vi.fn().mockResolvedValue(historyWithZeroMatch());
    const loadProfile = vi.fn().mockResolvedValue({
      present: false,
      draft_present: false,
      profile: null,
      active_attachment: null,
      pending_attachment: null,
    });
    const user = userEvent.setup();
    renderWithTheme(
      <App
        deps={{
          chat: {loadHistory, sendTurn: vi.fn(), saveAndEvaluateJob},
          sidebar: {loadProfile},
        }}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-empty-match-cta')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('jobagent-empty-match-cta'));
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-match-card')).toBeInTheDocument();
    });
    expect(saveAndEvaluateJob).toHaveBeenCalledWith(MSG_USER, undefined);
  });
});

describe('hydrate path still projects zero-result once', () => {
  it('history hydrate exposes exactly one zero-result host', () => {
    const page = historyWithZeroMatch();
    const hydrated = hydrateFromHistoryPage(page);
    let hosts = 0;
    for (let i = 0; i < hydrated.messages.length; i += 1) {
      if (hydrated.messages[i].role !== 'assistant') {
        continue;
      }
      const tools = toolsForAssistantDisplay(hydrated.messages, i);
      if (isZeroResultMatchJobs(tools)) {
        hosts += 1;
        expect(sourceMessageIdForAssistantDisplay(hydrated.messages, i)).toBe(
          MSG_USER,
        );
      }
    }
    expect(hosts).toBe(1);
  });

  it('two zero-result turns each bind their own initiating message id', () => {
    const page: HistoryPage = {
      items: [
        {
          id: MSG_USER,
          role: 'user',
          content: 'JD one',
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
            tool_executions: [toolExecution(zeroMatchData())],
          },
        },
        {
          id: MSG_ASST,
          role: 'assistant',
          content: 'a1',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
        {
          id: MSG_USER_B,
          role: 'user',
          content: 'JD two',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: {
            id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            user_message_id: MSG_USER_B,
            state: 'completed',
            pending_approval: null,
            error_code: null,
            completed_at: TS,
            created_at: TS,
            updated_at: TS,
            tool_executions: [
              toolExecution(zeroMatchData(), {
                id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
                tool_call_id: 'tc-2',
              }),
            ],
          },
        },
        {
          id: MSG_ASST_B,
          role: 'assistant',
          content: 'a2',
          structured_payload: null,
          created_at: TS,
          updated_at: TS,
          run: null,
        },
      ],
      next_cursor: null,
    };
    const hydrated = hydrateFromHistoryPage(page);
    const sources: string[] = [];
    for (let i = 0; i < hydrated.messages.length; i += 1) {
      if (hydrated.messages[i].role !== 'assistant') {
        continue;
      }
      const tools = toolsForAssistantDisplay(hydrated.messages, i);
      if (isZeroResultMatchJobs(tools)) {
        const sid = sourceMessageIdForAssistantDisplay(hydrated.messages, i);
        if (sid) {
          sources.push(sid);
        }
      }
    }
    expect(sources).toEqual([MSG_USER, MSG_USER_B]);
  });
});

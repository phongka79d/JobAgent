/**
 * Saved-JD sidebar panel: tab order, list/detail, currentness actions, a11y.
 * Composes accepted savedJobsState contracts without reimplementing transport.
 */
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
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {
  evaluateActionLabel,
  formatSavedJobLabel,
} from '../features/jobs/SavedJobDetail';
import {SavedJobsPanel} from '../features/jobs/SavedJobsPanel';
import {
  initialSavedJobsActionSlice,
  type CachedResource,
} from '../features/jobs/savedJobsState';
import type {
  SavedJobDetail,
  SavedJobListItem,
  SavedJobListPage,
} from '../features/jobs/types';
import {formatDisplayScore} from '../features/jobs/matchResult';
import {OBSERVABILITY_TABS} from '../features/observability/observabilityTabs';
import {ObservabilityTabList} from '../features/observability/ObservabilityTabList';
import type {ObservabilityTabId} from '../features/observability/types';
import {
  mockObservabilityApi,
  renderObservabilitySidebar,
} from './support/observability';

const JOB_NONE = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const JOB_STALE = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const JOB_CURRENT = 'cccccccc-dddd-4eee-8fff-000000000000';
const EVAL_ID = '11111111-2222-4333-8444-555555555555';
const TS = '2024-08-01T12:00:00.000Z';

const LONG_TITLE =
  'Principal Staff Backend Platform Reliability Engineering Lead for Distributed Systems';

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute('open');
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function matchResult(jobId: string, score: number) {
  return {
    jobId,
    title: 'Backend Engineer',
    company: 'Acme',
    location: 'Berlin',
    workMode: 'hybrid' as const,
    sourceUrl: null,
    finalScore: score,
    qualityMultiplier: 1,
    components: {
      semanticSimilarity: score,
      skillScore: null,
      seniorityScore: null,
      experienceScore: null,
      locationScore: null,
      workModeScore: null,
    },
    effectiveWeights: [{key: 'semantic_similarity' as const, weight: 1}],
    matchedRequiredSkills: [],
    matchedPreferredSkills: [],
    relatedSkills: [],
    missingRequiredSkills: [],
    summary: 'ok',
  };
}

function listItem(
  id: string,
  overrides: Partial<SavedJobListItem> = {},
): SavedJobListItem {
  return {
    id,
    title: `Title ${id.slice(0, 4)}`,
    company: 'Acme Corp',
    processing_status: 'processed',
    jd_quality: 'full',
    source_type: 'text',
    source_url: null,
    created_at: TS,
    updated_at: TS,
    evaluation_state: 'none',
    latest_score: null,
    ...overrides,
  };
}

function readyList(
  items: SavedJobListItem[],
): CachedResource<SavedJobListPage> {
  return {
    phase: items.length === 0 ? 'empty' : 'ready',
    data: {items, next_cursor: null},
    error: null,
    loaded: true,
  };
}

function readyDetail(
  job: SavedJobListItem,
  opts: {
    withEvaluation?: boolean;
    raw?: string | null;
  } = {},
): CachedResource<SavedJobDetail> {
  const withEvaluation =
    opts.withEvaluation ?? job.evaluation_state !== 'none';
  const score = job.latest_score ?? 0.72;
  return {
    phase: 'ready',
    data: {
      compact: job,
      extraction: {
        title: job.title,
        company: job.company,
        summary: 'Build reliable APIs and services for the platform.',
        responsibilities: ['Design services'],
        required_skills: [],
        preferred_skills: [],
        seniority: 'senior',
        min_experience_years: 5,
        max_experience_years: null,
        location: 'Berlin',
        work_mode: 'hybrid',
        extraction_confidence: 0.9,
      },
      raw_content: opts.raw === undefined ? 'raw jd text' : opts.raw,
      latest_evaluation: withEvaluation
        ? {
            id: EVAL_ID,
            job_id: job.id,
            evaluation_state:
              job.evaluation_state === 'stale' ? 'stale' : 'current',
            evaluation_context_hash: 'ctx-1',
            result: matchResult(job.id, score),
            created_at: TS,
            updated_at: TS,
          }
        : null,
    },
    error: null,
    loaded: true,
  };
}

function renderPanel(opts: {
  items: SavedJobListItem[];
  selectedJobId?: string | null;
  details?: Record<string, CachedResource<SavedJobDetail>>;
  pendingByJob?: Record<string, 'evaluate' | 'delete'>;
  errorsByJob?: Record<string, {code: string; summary: string}>;
  onSelect?: (id: string) => void;
  onEvaluate?: (
    id: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
  onConfirmDelete?: (
    id: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
}) {
  const selectedJobId =
    opts.selectedJobId === undefined
      ? (opts.items[0]?.id ?? null)
      : opts.selectedJobId;
  const details =
    opts.details ??
    Object.fromEntries(
      opts.items.map((item) => [item.id, readyDetail(item)]),
    );
  const onSelect = opts.onSelect ?? vi.fn();
  const onEvaluate = opts.onEvaluate ?? vi.fn().mockResolvedValue('success');
  const onConfirmDelete =
    opts.onConfirmDelete ?? vi.fn().mockResolvedValue('success');
  const onClearError = vi.fn();
  const onLoad = vi.fn();
  const onRefresh = vi.fn();
  const onRefreshDetail = vi.fn();

  render(
    <Theme theme={neutralTheme}>
      <SavedJobsPanel
        list={readyList(opts.items)}
        details={details}
        selectedJobId={selectedJobId}
        actions={{
          ...initialSavedJobsActionSlice,
          pendingByJob: opts.pendingByJob ?? {},
          errorsByJob: opts.errorsByJob ?? {},
        }}
        onSelect={onSelect}
        onLoad={onLoad}
        onRefresh={onRefresh}
        onEvaluate={onEvaluate}
        onConfirmDelete={onConfirmDelete}
        onClearError={onClearError}
        onRefreshDetail={onRefreshDetail}
      />
    </Theme>,
  );

  return {
    onSelect,
    onEvaluate,
    onConfirmDelete,
    onClearError,
    onRefresh,
    onRefreshDetail,
  };
}

describe('evaluateActionLabel currentness matrix', () => {
  it('maps none → Đánh giá với CV, stale → Đánh giá lại, current → null', () => {
    expect(evaluateActionLabel('none')).toBe('Đánh giá với CV');
    expect(evaluateActionLabel('stale')).toBe('Đánh giá lại');
    expect(evaluateActionLabel('current')).toBeNull();
  });
});

describe('observability tab order for JD đã lưu', () => {
  it('places JD đã lưu immediately after Agent runs', () => {
    const ids = OBSERVABILITY_TABS.map((tab) => tab.id);
    const runsIndex = ids.indexOf('runs');
    const savedIndex = ids.indexOf('saved-jobs');
    expect(runsIndex).toBeGreaterThanOrEqual(0);
    expect(savedIndex).toBe(runsIndex + 1);
    expect(OBSERVABILITY_TABS[savedIndex]?.label).toBe('JD đã lưu');
  });

  it('renders six vertical tabs with JD đã lưu after Agent runs', async () => {
    const onChange = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <ObservabilityTabList
          value="overview"
          isCollapsed={false}
          onChange={onChange}
        />
      </Theme>,
    );
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(6);
    const labels = tabs.map((tab) => tab.textContent ?? '');
    const runsAt = labels.findIndex((label) => label.includes('Agent runs'));
    const savedAt = labels.findIndex((label) => label.includes('JD đã lưu'));
    expect(savedAt).toBe(runsAt + 1);
  });
});

describe('SavedJobsPanel list, detail, and actions', () => {
  it('renders compact rows with processing badge, stale badge, and current score', () => {
    const none = listItem(JOB_NONE, {evaluation_state: 'none'});
    const stale = listItem(JOB_STALE, {
      title: LONG_TITLE,
      evaluation_state: 'stale',
      latest_score: 0.41,
    });
    const current = listItem(JOB_CURRENT, {
      evaluation_state: 'current',
      latest_score: 0.88,
    });
    renderPanel({items: [none, stale, current], selectedJobId: null});

    expect(screen.getByTestId('jobagent-obs-saved-jobs')).toBeInTheDocument();
    expect(
      screen.getByTestId(`jobagent-saved-job-stale-badge-${JOB_STALE}`),
    ).toHaveTextContent('Cần đánh giá lại');
    expect(
      screen.getByTestId(`jobagent-saved-job-score-${JOB_CURRENT}`),
    ).toHaveTextContent(formatDisplayScore(0.88));
    expect(
      screen.getByTestId(`jobagent-saved-job-eval-none-${JOB_NONE}`),
    ).toHaveTextContent('Chưa đánh giá');

    const longRow = screen.getByTestId(
      `jobagent-saved-job-select-${JOB_STALE}`,
    );
    expect(longRow).toHaveAttribute(
      'data-full-label',
      formatSavedJobLabel(stale),
    );
    expect(longRow.textContent).toContain(LONG_TITLE);
    expect(longRow.textContent).toContain('Acme Corp');
  });

  it('shows one selected detail with extraction and MatchCard for persisted result', async () => {
    const stale = listItem(JOB_STALE, {
      evaluation_state: 'stale',
      latest_score: 0.41,
    });
    renderPanel({items: [stale], selectedJobId: JOB_STALE});

    expect(screen.getByTestId('jobagent-saved-job-detail')).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-saved-job-extraction'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-saved-job-source')).toHaveTextContent(
      'raw jd text',
    );
    expect(screen.getByTestId('jobagent-match-card')).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-saved-job-stale-banner'),
    ).toHaveTextContent('Cần đánh giá lại');
    expect(screen.getByTestId('jobagent-match-final-score')).toHaveTextContent(
      formatDisplayScore(0.41),
    );
  });

  it('shows Đánh giá với CV for none and no evaluate for current', () => {
    const none = listItem(JOB_NONE, {evaluation_state: 'none'});
    const current = listItem(JOB_CURRENT, {
      evaluation_state: 'current',
      latest_score: 0.9,
    });

    const {rerender} = render(
      <Theme theme={neutralTheme}>
        <SavedJobsPanel
          list={readyList([none])}
          details={{[JOB_NONE]: readyDetail(none)}}
          selectedJobId={JOB_NONE}
          actions={initialSavedJobsActionSlice}
          onSelect={vi.fn()}
          onLoad={vi.fn()}
          onRefresh={vi.fn()}
          onEvaluate={vi.fn().mockResolvedValue('success')}
          onConfirmDelete={vi.fn().mockResolvedValue('success')}
          onClearError={vi.fn()}
          onRefreshDetail={vi.fn()}
        />
      </Theme>,
    );
    expect(
      screen.getByTestId(`jobagent-saved-job-evaluate-${JOB_NONE}`),
    ).toHaveTextContent('Đánh giá với CV');

    rerender(
      <Theme theme={neutralTheme}>
        <SavedJobsPanel
          list={readyList([current])}
          details={{[JOB_CURRENT]: readyDetail(current)}}
          selectedJobId={JOB_CURRENT}
          actions={initialSavedJobsActionSlice}
          onSelect={vi.fn()}
          onLoad={vi.fn()}
          onRefresh={vi.fn()}
          onEvaluate={vi.fn().mockResolvedValue('success')}
          onConfirmDelete={vi.fn().mockResolvedValue('success')}
          onClearError={vi.fn()}
          onRefreshDetail={vi.fn()}
        />
      </Theme>,
    );
    expect(
      screen.queryByTestId(`jobagent-saved-job-evaluate-${JOB_CURRENT}`),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId(`jobagent-saved-job-delete-${JOB_CURRENT}`),
    ).toBeInTheDocument();
  });

  it('shows Đánh giá lại only for stale and disables while pending', async () => {
    const stale = listItem(JOB_STALE, {
      evaluation_state: 'stale',
      latest_score: 0.3,
    });
    const onEvaluate = vi.fn().mockResolvedValue('success');
    renderPanel({
      items: [stale],
      selectedJobId: JOB_STALE,
      pendingByJob: {[JOB_STALE]: 'evaluate'},
      onEvaluate,
    });

    const evaluateBtn = screen.getByTestId(
      `jobagent-saved-job-evaluate-${JOB_STALE}`,
    );
    expect(evaluateBtn).toHaveTextContent('Đánh giá lại');
    expect(evaluateBtn).toBeDisabled();
    expect(
      screen.getByTestId(`jobagent-saved-job-delete-${JOB_STALE}`),
    ).toBeDisabled();
  });

  it('names the Job in delete confirmation and calls confirmDelete', async () => {
    const job = listItem(JOB_NONE, {
      title: 'Platform Engineer',
      company: 'Nimbus',
    });
    const onConfirmDelete = vi.fn().mockResolvedValue('success');
    renderPanel({
      items: [job],
      selectedJobId: JOB_NONE,
      onConfirmDelete,
    });

    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-delete-${JOB_NONE}`),
    );
    const dialog = await screen.findByTestId(
      'jobagent-saved-job-delete-dialog',
    );
    expect(dialog).toHaveTextContent('Platform Engineer · Nimbus');
    expect(dialog).toHaveTextContent('Xoá JD');

    const action = within(dialog).getByRole('button', {name: 'Xoá JD'});
    await userEvent.click(action);
    await waitFor(() => {
      expect(onConfirmDelete).toHaveBeenCalledWith(JOB_NONE);
    });
  });

  it('keeps prior list data visible when list is in error phase with cached items', () => {
    const job = listItem(JOB_NONE);
    render(
      <Theme theme={neutralTheme}>
        <SavedJobsPanel
          list={{
            phase: 'error',
            data: {items: [job], next_cursor: null},
            error: {code: 'REQUEST_FAILED', summary: 'Network down'},
            loaded: true,
          }}
          details={{}}
          selectedJobId={null}
          actions={initialSavedJobsActionSlice}
          onSelect={vi.fn()}
          onLoad={vi.fn()}
          onRefresh={vi.fn()}
          onEvaluate={vi.fn().mockResolvedValue('success')}
          onConfirmDelete={vi.fn().mockResolvedValue('success')}
          onClearError={vi.fn()}
          onRefreshDetail={vi.fn()}
        />
      </Theme>,
    );
    expect(screen.getByTestId('jobagent-obs-saved-jobs-error')).toHaveTextContent(
      'Network down',
    );
    expect(
      screen.getByTestId(`jobagent-saved-job-select-${JOB_NONE}`),
    ).toBeInTheDocument();
  });

  it('shows empty state without redundant match heading when no jobs', () => {
    renderPanel({items: [], selectedJobId: null});
    expect(
      screen.getByTestId('jobagent-obs-saved-jobs-empty'),
    ).toHaveTextContent('Chưa có JD đã lưu');
    expect(screen.queryByTestId('jobagent-match-card')).not.toBeInTheDocument();
  });

  it('surfaces action errors and allows dismiss', async () => {
    const job = listItem(JOB_NONE, {evaluation_state: 'none'});
    const onClearError = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <SavedJobsPanel
          list={readyList([job])}
          details={{[JOB_NONE]: readyDetail(job)}}
          selectedJobId={JOB_NONE}
          actions={{
            ...initialSavedJobsActionSlice,
            errorsByJob: {
              [JOB_NONE]: {
                code: 'EVALUATION_UNAVAILABLE',
                summary: 'No active CV',
              },
            },
          }}
          onSelect={vi.fn()}
          onLoad={vi.fn()}
          onRefresh={vi.fn()}
          onEvaluate={vi.fn().mockResolvedValue('error')}
          onConfirmDelete={vi.fn().mockResolvedValue('success')}
          onClearError={onClearError}
          onRefreshDetail={vi.fn()}
        />
      </Theme>,
    );
    expect(
      screen.getByTestId(`jobagent-saved-job-action-error-${JOB_NONE}`),
    ).toHaveTextContent('No active CV');
    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-clear-error-${JOB_NONE}`),
    );
    expect(onClearError).toHaveBeenCalledWith(JOB_NONE);
  });
});

describe('sidebar composition loads JD đã lưu panel', () => {
  it('opens the saved-jobs tab after Agent runs and loads list via API', async () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    // @ts-expect-error test mutation of Vite env
    import.meta.env.VITE_API_BASE_URL = 'http://api.test';

    try {
      const listItemPayload = {
        id: JOB_NONE,
        title: 'Sidebar Job',
        company: 'Acme',
        processing_status: 'processed',
        jd_quality: 'full',
        source_type: 'text',
        source_url: null,
        created_at: TS,
        updated_at: TS,
        evaluation_state: 'none',
        latest_score: null,
      };
      const listPage = {items: [listItemPayload], next_cursor: null};

      const fetchMock = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(async (input: RequestInfo | URL) => {
          const url = String(input);
          if (url.includes('/api/jobs/') && url.includes(JOB_NONE)) {
            return new Response(
              JSON.stringify({
                compact: listItemPayload,
                extraction: null,
                raw_content: null,
                latest_evaluation: null,
              }),
              {status: 200, headers: {'Content-Type': 'application/json'}},
            );
          }
          if (url.includes('/api/jobs')) {
            return new Response(JSON.stringify(listPage), {
              status: 200,
              headers: {'Content-Type': 'application/json'},
            });
          }
          return new Response(JSON.stringify({}), {
            status: 404,
            headers: {'Content-Type': 'application/json'},
          });
        });

      renderObservabilitySidebar(mockObservabilityApi());

      const tabs = await screen.findAllByRole('tab');
      expect(tabs).toHaveLength(6);
      const runs = screen.getByRole('tab', {name: 'Agent runs'});
      const saved = screen.getByRole('tab', {name: 'JD đã lưu'});
      expect(tabs.indexOf(saved)).toBe(tabs.indexOf(runs) + 1);

      await userEvent.click(saved);
      expect(
        await screen.findByTestId('jobagent-obs-saved-jobs'),
      ).toBeInTheDocument();

      await waitFor(() => {
        const jobUrls = fetchMock.mock.calls
          .map((call) => String(call[0]))
          .filter((url) => url.includes('/api/jobs'));
        expect(jobUrls.length).toBeGreaterThan(0);
      });

      expect(
        await screen.findByTestId(`jobagent-saved-job-select-${JOB_NONE}`),
      ).toHaveTextContent('Sidebar Job');

      await userEvent.click(
        screen.getByTestId(`jobagent-saved-job-select-${JOB_NONE}`),
      );
      await waitFor(() => {
        expect(
          screen.getByTestId(`jobagent-saved-job-evaluate-${JOB_NONE}`),
        ).toHaveTextContent('Đánh giá với CV');
      });
    } finally {
      // @ts-expect-error restore Vite env
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

describe('OBSERVABILITY_TABS keyboard identity', () => {
  it('supports selecting saved-jobs via tab change', async () => {
    let value: ObservabilityTabId = 'runs';
    const onChange = vi.fn((next: ObservabilityTabId) => {
      value = next;
    });
    const {rerender} = render(
      <Theme theme={neutralTheme}>
        <ObservabilityTabList
          value={value}
          isCollapsed={false}
          onChange={onChange}
        />
      </Theme>,
    );
    await userEvent.click(screen.getByRole('tab', {name: 'JD đã lưu'}));
    expect(onChange).toHaveBeenCalledWith('saved-jobs');
    rerender(
      <Theme theme={neutralTheme}>
        <ObservabilityTabList
          value="saved-jobs"
          isCollapsed={false}
          onChange={onChange}
        />
      </Theme>,
    );
    expect(screen.getByRole('tab', {name: 'JD đã lưu'})).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});

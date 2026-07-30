/**
 * Saved-JD product panel: list/detail, currentness actions, and accessibility.
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
import {StrictMode} from 'react';
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

const JOB_NONE = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const JOB_STALE = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff';
const JOB_CURRENT = 'cccccccc-dddd-4eee-8fff-000000000000';
const EVAL_ID = '11111111-2222-4333-8444-555555555555';
const TS = '2024-08-01T12:00:00.000Z';
const SERVER_JOB_LABEL = 'Quarterly Revenue Systems Lead';

const LONG_TITLE =
  'Principal Staff Backend Platform Reliability Engineering Lead for Distributed Systems';
const LONG_DISPLAY_LABEL = 'Platform reliability leadership';

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
    displayLabel: 'Backend Engineer · Acme',
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
    title: 'Backend Engineer',
    company: 'Acme Corp',
    display_label: SERVER_JOB_LABEL,
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
        responsibilities: ['Design services', 'Own on-call'],
        required_skills: [
          {
            skill: {
              canonical_key: 'python',
              display_name: 'Python',
              aliases: [],
              category: 'language',
            },
            confidence: 0.91,
            evidence: ['Required: Python 3+'],
          },
        ],
        preferred_skills: [
          {
            skill: {
              canonical_key: 'kubernetes',
              display_name: 'Kubernetes',
              aliases: [],
              category: 'platform',
            },
            confidence: 0.7,
            evidence: ['Nice to have: Kubernetes'],
          },
        ],
        seniority: 'senior',
        min_experience_years: 5,
        max_experience_years: 8,
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
  pendingByJob?: Record<string, 'evaluate' | 'delete' | 'reextract'>;
  errorsByJob?: Record<string, {code: string; summary: string}>;
  onSelect?: (id: string) => void;
  onEvaluate?: (
    id: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
  onConfirmDelete?: (
    id: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
  onConfirmReextract?: (
    id: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
  canCreateTailoredCv?: boolean;
  isTailoringPending?: boolean;
  onCreateTailoredCv?: (id: string) => void;
  strictMode?: boolean;
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
  const onConfirmReextract =
    opts.onConfirmReextract ?? vi.fn().mockResolvedValue('success');
  const onClearError = vi.fn();
  const onLoad = vi.fn();
  const onRefresh = vi.fn();
  const onRefreshDetail = vi.fn();

  const panel = (
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
        onConfirmReextract={onConfirmReextract}
        onClearError={onClearError}
        onRefreshDetail={onRefreshDetail}
        canCreateTailoredCv={opts.canCreateTailoredCv}
        isTailoringPending={opts.isTailoringPending}
        onCreateTailoredCv={opts.onCreateTailoredCv}
      />
    </Theme>
  );
  render(opts.strictMode ? <StrictMode>{panel}</StrictMode> : panel);

  return {
    onSelect,
    onEvaluate,
    onConfirmDelete,
    onConfirmReextract,
    onClearError,
    onRefresh,
    onRefreshDetail,
  };
}

describe('evaluateActionLabel currentness matrix', () => {
  it('maps none to Evaluate with CV, stale to Re-evaluate, and current to null', () => {
    expect(evaluateActionLabel('none')).toBe('Evaluate with CV');
    expect(evaluateActionLabel('stale')).toBe('Re-evaluate');
    expect(evaluateActionLabel('current')).toBeNull();
  });
});

describe('SavedJobsPanel list, detail, and actions', () => {
  it('uses a master-detail workspace and opens the CV comparison first', () => {
    const current = listItem(JOB_CURRENT, {
      evaluation_state: 'current',
      latest_score: 0.536,
    });

    renderPanel({items: [current], selectedJobId: JOB_CURRENT});

    expect(
      screen.getByTestId('jobagent-saved-jobs-master-pane'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-saved-jobs-detail-pane'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', {name: 'CV match'}),
    ).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('jobagent-match-card')).toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-saved-job-extraction'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-saved-job-source'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-match-metadata'),
    ).not.toBeInTheDocument();
  });

  it('shows the tailored-CV action only for unlocked processed full or partial JDs', async () => {
    const onCreateTailoredCv = vi.fn();
    renderPanel({
      items: [listItem(JOB_NONE, {jd_quality: 'partial'})],
      selectedJobId: JOB_NONE,
      canCreateTailoredCv: true,
      onCreateTailoredCv,
    });
    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-tailor-${JOB_NONE}`),
    );
    expect(onCreateTailoredCv).toHaveBeenCalledWith(JOB_NONE);

    cleanup();
    renderPanel({
      items: [listItem(JOB_NONE, {processing_status: 'processing'})],
      selectedJobId: JOB_NONE,
      canCreateTailoredCv: true,
      onCreateTailoredCv,
    });
    expect(
      screen.queryByTestId(`jobagent-saved-job-tailor-${JOB_NONE}`),
    ).not.toBeInTheDocument();
  });

  it('renders compact rows with processing badge, stale badge, and current score', () => {
    const none = listItem(JOB_NONE, {evaluation_state: 'none'});
    const stale = listItem(JOB_STALE, {
      title: LONG_TITLE,
      display_label: LONG_DISPLAY_LABEL,
      evaluation_state: 'stale',
      latest_score: 0.41,
    });
    const current = listItem(JOB_CURRENT, {
      evaluation_state: 'current',
      latest_score: 0.88,
    });
    renderPanel({items: [none, stale, current], selectedJobId: null});

    expect(screen.getByTestId('jobagent-saved-jobs')).toBeInTheDocument();
    const serverLabelRow = screen.getByTestId(
      `jobagent-saved-job-select-${JOB_NONE}`,
    );
    expect(serverLabelRow).toHaveTextContent(SERVER_JOB_LABEL);
    expect(serverLabelRow).not.toHaveTextContent(JOB_NONE);
    expect(serverLabelRow).not.toHaveTextContent(JOB_NONE.slice(0, 8));
    expect(
      screen.getByTestId(`jobagent-saved-job-stale-badge-${JOB_STALE}`),
    ).toHaveTextContent('Needs re-evaluation');
    expect(
      screen.getByTestId(`jobagent-saved-job-score-${JOB_CURRENT}`),
    ).toHaveTextContent(formatDisplayScore(0.88));
    expect(
      screen.getByTestId(`jobagent-saved-job-eval-none-${JOB_NONE}`),
    ).toHaveTextContent('Not evaluated');

    const longRow = screen.getByTestId(
      `jobagent-saved-job-select-${JOB_STALE}`,
    );
    expect(longRow).toHaveAttribute(
      'data-full-label',
      formatSavedJobLabel(stale),
    );
    expect(longRow.textContent).toContain(LONG_DISPLAY_LABEL);
    expect(longRow.textContent).not.toContain(LONG_TITLE);
  });

  it('keeps each list row concise with one company label and English status', () => {
    const current = listItem(JOB_CURRENT, {
      title: 'AI Engineer',
      company: 'MISA',
      jd_quality: 'partial',
      evaluation_state: 'current',
      latest_score: 0.536,
    });

    renderPanel({items: [current], selectedJobId: null});

    const row = screen.getByTestId(
      `jobagent-saved-job-select-${JOB_CURRENT}`,
    );
    expect(row).toHaveTextContent('Processed · Partial');
    expect(row.textContent?.match(/MISA/g)).toHaveLength(1);
    expect(row).not.toHaveTextContent('processed');
    expect(row).not.toHaveTextContent('partial');
    expect(row).not.toHaveTextContent('current');
  });

  it('presents selected job metadata consistently in English', () => {
    const current = listItem(JOB_CURRENT, {
      jd_quality: 'partial',
      source_type: 'text',
      evaluation_state: 'current',
      latest_score: 0.536,
    });

    renderPanel({items: [current], selectedJobId: JOB_CURRENT});

    const metadata = screen.getByTestId('jobagent-saved-job-detail-meta');
    expect(metadata).toHaveTextContent('Processed');
    expect(metadata).toHaveTextContent('Partial');
    expect(metadata).toHaveTextContent('Text');
    expect(metadata).toHaveTextContent('Current');
    expect(metadata).not.toHaveTextContent('processed');
    expect(metadata).not.toHaveTextContent('partial');
    expect(metadata).not.toHaveTextContent('current');
  });

  it('shows one selected detail with extraction and MatchCard for persisted result', async () => {
    const stale = listItem(JOB_STALE, {
      display_label: SERVER_JOB_LABEL,
      evaluation_state: 'stale',
      latest_score: 0.41,
    });
    renderPanel({items: [stale], selectedJobId: JOB_STALE});

    const detail = screen.getByTestId('jobagent-saved-job-detail');
    expect(detail).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-match-card')).toBeInTheDocument();
    expect(detail).toHaveTextContent(SERVER_JOB_LABEL);
    expect(detail).not.toHaveTextContent(JOB_STALE);
    expect(detail).not.toHaveTextContent(JOB_STALE.slice(0, 8));
    expect(
      screen.getByTestId('jobagent-saved-job-stale-banner'),
    ).toHaveTextContent('Re-evaluation needed');
    expect(screen.getByTestId('jobagent-match-final-score')).toHaveTextContent(
      formatDisplayScore(0.41),
    );

    await userEvent.click(screen.getByRole('tab', {name: 'Job overview'}));
    expect(
      screen.getByTestId('jobagent-saved-job-extraction'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-match-card')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', {name: 'Source text'}));
    expect(screen.getByTestId('jobagent-saved-job-source')).toHaveTextContent(
      'raw jd text',
    );
  });

  it('renders an explicit empty summary with metadata retained', async () => {
    const unscorable = listItem(JOB_NONE, {
      title: 'Contact form role',
      company: 'Sparse Co',
      processing_status: 'processed',
      jd_quality: 'unscorable',
      evaluation_state: 'none',
      source_type: 'url',
      source_url: 'https://example.com',
    });
    const detail = readyDetail(unscorable, {
      withEvaluation: false,
      raw: 'Please email careers@example.com',
    });
    detail.data!.extraction = {
      ...detail.data!.extraction!,
      title: 'Contact form role',
      company: 'Sparse Co',
      summary: '',
      seniority: 'unknown',
      work_mode: 'unknown',
      location: null,
      extraction_confidence: 0.1,
    };

    renderPanel({
      items: [unscorable],
      selectedJobId: JOB_NONE,
      details: {[JOB_NONE]: detail},
    });

    await userEvent.click(screen.getByRole('tab', {name: 'Job overview'}));
    const extraction = screen.getByTestId('jobagent-saved-job-extraction');
    expect(extraction).toHaveTextContent('No summary available');
    expect(extraction).toHaveTextContent('Contact form role');
    expect(extraction).toHaveTextContent('Sparse Co');
    expect(extraction).toHaveTextContent('Unknown');
    await userEvent.click(screen.getByRole('tab', {name: 'Source text'}));
    expect(screen.getByTestId('jobagent-saved-job-source')).toHaveTextContent(
      'Please email careers@example.com',
    );
    expect(screen.getByTestId('jobagent-saved-job-detail-meta')).toHaveTextContent(
      'Not scorable',
    );
    expect(
      screen.queryByText(/INVALID_SAVED_JOB_DETAIL_PAYLOAD/),
    ).not.toBeInTheDocument();
  });

  it('renders an explicit empty summary for whitespace-only extraction summary', async () => {
    const job = listItem(JOB_NONE, {
      evaluation_state: 'none',
      jd_quality: 'unscorable',
    });
    const detail = readyDetail(job, {withEvaluation: false});
    detail.data!.extraction = {
      ...detail.data!.extraction!,
      summary: '  \n\t  ',
    };

    renderPanel({
      items: [job],
      selectedJobId: JOB_NONE,
      details: {[JOB_NONE]: detail},
    });

    await userEvent.click(screen.getByRole('tab', {name: 'Job overview'}));
    expect(
      screen.getByTestId('jobagent-saved-job-extraction'),
    ).toHaveTextContent('No summary available');
    await userEvent.click(screen.getByRole('tab', {name: 'Source text'}));
    expect(screen.getByTestId('jobagent-saved-job-source')).toHaveTextContent(
      'raw jd text',
    );
  });

  it('shows Evaluate with CV for none and no evaluate for current', () => {
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
          onConfirmReextract={vi.fn().mockResolvedValue('success')}
          onClearError={vi.fn()}
          onRefreshDetail={vi.fn()}
        />
      </Theme>,
    );
    expect(
      screen.getByTestId(`jobagent-saved-job-evaluate-${JOB_NONE}`),
    ).toHaveTextContent('Evaluate with CV');

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
          onConfirmReextract={vi.fn().mockResolvedValue('success')}
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

  it('shows Re-evaluate only for stale and disables while pending', async () => {
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
    expect(evaluateBtn).toHaveTextContent('Re-evaluate');
    expect(evaluateBtn).toBeDisabled();
    expect(
      screen.getByTestId(`jobagent-saved-job-delete-${JOB_STALE}`),
    ).toBeDisabled();
  });

  it('uses the server label, never an ID fallback, in the delete confirmation', async () => {
    const job = listItem(JOB_NONE, {
      title: 'Platform Engineer',
      company: 'Nimbus',
      display_label: SERVER_JOB_LABEL,
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
    expect(dialog).toHaveTextContent(SERVER_JOB_LABEL);
    expect(dialog).not.toHaveTextContent(JOB_NONE);
    expect(dialog).not.toHaveTextContent(JOB_NONE.slice(0, 8));
    expect(dialog).toHaveTextContent('Delete job');

    const action = within(dialog).getByRole('button', {name: 'Delete job'});
    await userEvent.click(action);
    await waitFor(() => {
      expect(onConfirmDelete).toHaveBeenCalledWith(JOB_NONE);
    });
  });

  it('mounts an open delete dialog only after selecting a target in StrictMode', async () => {
    const job = listItem(JOB_NONE, {
      title: 'Platform Engineer',
      company: 'Nimbus',
      display_label: 'Platform Engineer · Nimbus',
    });
    renderPanel({
      items: [job],
      selectedJobId: JOB_NONE,
      strictMode: true,
    });

    expect(
      screen.queryByTestId('jobagent-saved-job-delete-dialog'),
    ).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-delete-${JOB_NONE}`),
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-saved-job-delete-dialog'),
      ).toHaveAttribute('open');
    });
    expect(
      screen.getByTestId('jobagent-saved-job-delete-dialog'),
    ).toHaveTextContent('Platform Engineer · Nimbus');
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
          onConfirmReextract={vi.fn().mockResolvedValue('success')}
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

  it('shows English empty state without redundant match heading when no jobs', () => {
    renderPanel({items: [], selectedJobId: null});
    expect(
      screen.getByTestId('jobagent-obs-saved-jobs-empty'),
    ).toHaveTextContent('No saved jobs yet');
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
          onConfirmReextract={vi.fn().mockResolvedValue('success')}
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

  it('renders every extraction group with experience, skills, and confidence', async () => {
    const job = listItem(JOB_CURRENT, {
      evaluation_state: 'current',
      latest_score: 0.88,
    });
    renderPanel({items: [job], selectedJobId: JOB_CURRENT});

    await userEvent.click(screen.getByRole('tab', {name: 'Job overview'}));
    const extraction = screen.getByTestId('jobagent-saved-job-extraction');
    expect(
      screen.getByTestId('jobagent-saved-job-extraction-metadata'),
    ).toBeInTheDocument();
    expect(extraction).toHaveTextContent('Job information');
    expect(extraction).toHaveTextContent('5–8 years');
    expect(extraction).toHaveTextContent('0.90');
    expect(
      screen.getByTestId('jobagent-saved-job-responsibilities'),
    ).toHaveTextContent('Design services');
    expect(
      screen.getByTestId('jobagent-saved-job-required-skills'),
    ).toHaveTextContent('Python');
    expect(
      screen.getByTestId('jobagent-saved-job-preferred-skills'),
    ).toHaveTextContent('Kubernetes');
    expect(screen.getByTestId('jobagent-saved-job-evidence')).toHaveTextContent(
      'Evidence (2)',
    );
  });

  it('shows explicit empty states and keeps evidence collapsed by default', async () => {
    const job = listItem(JOB_NONE, {evaluation_state: 'none'});
    const detail = readyDetail(job, {withEvaluation: false});
    detail.data!.extraction = {
      ...detail.data!.extraction!,
      responsibilities: [],
      required_skills: [],
      preferred_skills: [],
      min_experience_years: null,
      max_experience_years: null,
      location: null,
      title: null,
      company: null,
    };

    renderPanel({
      items: [job],
      selectedJobId: JOB_NONE,
      details: {[JOB_NONE]: detail},
    });

    await userEvent.click(screen.getByRole('tab', {name: 'Job overview'}));
    expect(
      screen.getByTestId('jobagent-saved-job-responsibilities-empty'),
    ).toHaveTextContent('No responsibilities were extracted');
    expect(
      screen.getByTestId('jobagent-saved-job-required-skills'),
    ).toHaveTextContent('No required skills were extracted');
    expect(
      screen.getByTestId('jobagent-saved-job-preferred-skills'),
    ).toHaveTextContent('No preferred skills were extracted');
    expect(
      screen.getByTestId('jobagent-saved-job-extraction-metadata'),
    ).toHaveTextContent('Unknown');

    // Collapsible starts closed: trigger is aria-expanded=false; content is not shown.
    const evidenceTrigger = screen.getByRole('button', {
      name: /Evidence \(0\)/,
    });
    expect(evidenceTrigger).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(evidenceTrigger);
    expect(evidenceTrigger).toHaveAttribute('aria-expanded', 'true');
    expect(
      await screen.findByTestId('jobagent-saved-job-evidence-empty'),
    ).toHaveTextContent('No evidence available');
  });

  it('names the Job in re-extract dialog, states consequences, and confirms', async () => {
    const job = listItem(JOB_NONE, {
      title: 'Platform Engineer',
      company: 'Nimbus',
      display_label: 'Platform Engineer · Nimbus',
    });
    const onConfirmReextract = vi.fn().mockResolvedValue('success');
    renderPanel({
      items: [job],
      selectedJobId: JOB_NONE,
      onConfirmReextract,
    });

    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-reextract-${JOB_NONE}`),
    );
    const dialog = await screen.findByTestId(
      'jobagent-saved-job-reextract-dialog',
    );
    expect(dialog).toHaveTextContent('Platform Engineer · Nimbus');
    expect(dialog).toHaveTextContent('identity and raw source are preserved');
    expect(dialog).toHaveTextContent('fails before commit');
    expect(dialog).toHaveTextContent('evaluation becomes stale');
    expect(dialog).toHaveTextContent('not run automatically');

    const action = within(dialog).getByRole('button', {
      name: 'Re-extract JD',
    });
    await userEvent.click(action);
    await waitFor(() => {
      expect(onConfirmReextract).toHaveBeenCalledWith(JOB_NONE);
    });
  });

  it('cancels re-extract without calling confirm and locks while pending', async () => {
    const job = listItem(JOB_STALE, {
      evaluation_state: 'stale',
      latest_score: 0.3,
      title: 'SRE',
      company: 'Acme',
    });
    const onConfirmReextract = vi.fn().mockResolvedValue('success');
    renderPanel({
      items: [job],
      selectedJobId: JOB_STALE,
      onConfirmReextract,
    });

    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-reextract-${JOB_STALE}`),
    );
    const dialog = await screen.findByTestId(
      'jobagent-saved-job-reextract-dialog',
    );
    const cancel = within(dialog).getByRole('button', {name: 'Cancel'});
    await userEvent.click(cancel);
    expect(onConfirmReextract).not.toHaveBeenCalled();

    cleanup();
    renderPanel({
      items: [job],
      selectedJobId: JOB_STALE,
      pendingByJob: {[JOB_STALE]: 'reextract'},
      onConfirmReextract,
    });
    expect(
      screen.getByTestId(`jobagent-saved-job-reextract-${JOB_STALE}`),
    ).toBeDisabled();
    expect(
      screen.getByTestId(`jobagent-saved-job-delete-${JOB_STALE}`),
    ).toBeDisabled();
    expect(screen.getByText('Extracting…')).toBeInTheDocument();
  });

  it('shows graph rebuild guidance banner for NEO4J_SYNC_FAILED after reextract', () => {
    const job = listItem(JOB_NONE, {evaluation_state: 'stale'});
    renderPanel({
      items: [job],
      selectedJobId: JOB_NONE,
      errorsByJob: {
        [JOB_NONE]: {
          code: 'NEO4J_SYNC_FAILED',
          summary: 'Restore Neo4j and run local graph rebuild.',
        },
      },
    });
    const banner = screen.getByTestId(
      `jobagent-saved-job-action-error-${JOB_NONE}`,
    );
    expect(banner).toHaveTextContent('Related data needs recovery');
    expect(banner).toHaveTextContent('local graph rebuild');
  });
});


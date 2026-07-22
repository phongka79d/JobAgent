import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {cleanup, render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {CachedResource as JobResource} from '../features/jobs/savedJobsState';
import type {
  SelectedJobSkillMap,
  SkillCompatibilityItem,
} from '../features/jobs/types';
import {GraphPanel} from '../features/observability/GraphPanel';
import type {CachedResource as GraphResource} from '../features/observability/state';
import type {GraphSnapshot} from '../features/observability/types';
import {graphReady, installMatchMedia} from './support/observability';

const JOB_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const TS = '2024-08-01T12:00:00.000Z';

function assertion(key: string, label: string, evidence: string) {
  return {
    canonical_key: key,
    display_name: label,
    confidence: 0.9,
    evidence: [evidence],
  };
}

function item(
  matchType: SkillCompatibilityItem['match_type'],
): SkillCompatibilityItem {
  if (matchType === 'direct') {
    return {
      match_type: 'direct',
      requirement: 'required',
      strength: 1,
      candidate_skill: assertion(
        'audience_research',
        'Audience Research',
        'Candidate evidence direct',
      ),
      job_skill: assertion(
        'audience_research',
        'Nghiên cứu khách hàng',
        'JD evidence direct',
      ),
      relationship: null,
    };
  }
  if (matchType === 'related') {
    return {
      match_type: 'related',
      requirement: 'preferred',
      strength: 0.6,
      candidate_skill: assertion(
        'service_research',
        'Service Design/Research',
        'Candidate evidence related',
      ),
      job_skill: assertion(
        'customer_discovery',
        'Khám phá nhu cầu',
        'JD evidence related',
      ),
      relationship: {
        from_key: 'service_research',
        to_key: 'customer_discovery',
        weight: 0.75,
        source: 'seed',
      },
    };
  }
  if (matchType === 'missing_required') {
    return {
      match_type: 'missing_required',
      requirement: 'required',
      strength: 0,
      candidate_skill: null,
      job_skill: assertion(
        'budget_ownership',
        'Quản lý ngân sách',
        'JD evidence required',
      ),
      relationship: null,
    };
  }
  if (matchType === 'missing_preferred') {
    return {
      match_type: 'missing_preferred',
      requirement: 'preferred',
      strength: 0,
      candidate_skill: null,
      job_skill: assertion(
        'partner_enablement',
        'Partner Enablement+',
        'JD evidence preferred',
      ),
      relationship: null,
    };
  }
  return {
    match_type: 'candidate_only',
    requirement: 'none',
    strength: 0,
    candidate_skill: assertion(
      'clinical_coordination',
      'Điều phối lâm sàng',
      'Candidate evidence additional',
    ),
    job_skill: null,
    relationship: null,
  };
}

function readyMap(): SelectedJobSkillMap {
  const items = [
    item('direct'),
    item('related'),
    item('missing_required'),
    item('missing_preferred'),
    item('candidate_only'),
  ];
  return {
    status: 'ready',
    code: null,
    summary: 'Selected map is ready.',
    rebuild_instruction: null,
    candidate: {
      id: 'active',
      attachment_id: '11111111-2222-4333-8444-555555555555',
      current_title: 'Điều phối viên',
      revision: TS,
    },
    job: {
      id: JOB_ID,
      title: 'Campaign Operations',
      company: 'Synthetic Co',
      revision: TS,
    },
    items,
    counts: {
      direct: 1,
      related: 1,
      missing_required: 1,
      missing_preferred: 1,
      candidate_only: 1,
    },
    checked_at: TS,
  };
}

function mapResource(
  map: SelectedJobSkillMap | null,
  overrides: Partial<JobResource<SelectedJobSkillMap>> = {},
): JobResource<SelectedJobSkillMap> {
  return {
    phase: map ? 'ready' : 'idle',
    data: map,
    error: null,
    loaded: Boolean(map),
    ...overrides,
  };
}

function graphResource(): GraphResource<GraphSnapshot> {
  return {
    phase: 'ready',
    data: graphReady(),
    error: null,
    loaded: true,
  };
}

function renderPanel(
  selectedJobId: string | null = JOB_ID,
  resource: JobResource<SelectedJobSkillMap> | null = mapResource(readyMap()),
) {
  render(
    <Theme theme={neutralTheme}>
      <GraphPanel
        resource={graphResource()}
        selectedJobId={selectedJobId}
        skillMapResource={resource}
        onRefresh={vi.fn()}
        onRefreshSkillMap={vi.fn()}
      />
    </Theme>,
  );
}

afterEach(() => {
  cleanup();
  installMatchMedia(false);
});

describe('selected CV/JD compatibility map', () => {
  it('defaults to readable backend facts with five filters and source evidence', async () => {
    renderPanel();

    expect(
      screen.getByRole('radio', {name: 'Phù hợp CV–JD'}),
    ).toBeChecked();
    for (const label of [
      'Khớp chính xác (1)',
      'Liên quan (1)',
      'Thiếu bắt buộc (1)',
      'Ưu tiên chưa có (1)',
      'Kỹ năng bổ sung (1)',
    ]) {
      expect(screen.getByRole('button', {name: label})).toBeInTheDocument();
    }
    expect(screen.getByText('Điều phối viên')).toBeInTheDocument();
    expect(screen.getByText('Campaign Operations')).toBeInTheDocument();
    expect(screen.getAllByText(/Nghiên cứu khách h/).length).toBeGreaterThan(0);
    expect(screen.queryByText('audience_research')).not.toBeInTheDocument();
    expect(screen.queryByText(JOB_ID)).not.toBeInTheDocument();
    expect(screen.queryByText('HAS_SKILL')).not.toBeInTheDocument();

    await userEvent.click(screen.getAllByText(/Nghiên cứu khách h/)[0]!);
    const evidence = screen.getByTestId('jobagent-skill-map-evidence');
    expect(evidence).toHaveTextContent('Candidate evidence direct');
    expect(evidence).toHaveTextContent('JD evidence direct');

    await userEvent.click(
      screen.getByRole('button', {name: 'Thiếu bắt buộc (1)'}),
    );
    const list = screen.getByTestId('jobagent-skill-map-items');
    expect(within(list).getByText('Quản lý ngân sách')).toBeInTheDocument();
    expect(within(list).queryAllByText(/Nghiên cứu khách h/)).toHaveLength(0);
  });

  it('keeps the existing technical inspector behind the explicit switch', async () => {
    renderPanel();

    await userEvent.click(screen.getByRole('radio', {name: 'Kỹ thuật'}));

    expect(
      await screen.findByRole('group', {
        name: 'Candidate, jobs and skills network',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Fit view'})).toBeInTheDocument();
    expect(
      screen.getByTestId('jobagent-graph-node-skill:python'),
    ).toHaveTextContent('Python');
  });

  it('shows explicit no-job and stale states without partial items', () => {
    renderPanel(null, null);
    expect(screen.getByText('Chưa chọn JD')).toBeInTheDocument();
    cleanup();

    const stale = readyMap();
    stale.status = 'stale';
    stale.code = 'NEO4J_REBUILD_REQUIRED';
    stale.rebuild_instruction = 'Rebuild Neo4j from SQLite.';
    stale.items = [];
    stale.counts = {
      direct: 0,
      related: 0,
      missing_required: 0,
      missing_preferred: 0,
      candidate_only: 0,
    };
    renderPanel(JOB_ID, mapResource(stale));

    expect(screen.getByText(/Rebuild Neo4j from SQLite/)).toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-skill-map-items')).not.toBeInTheDocument();
  });
});

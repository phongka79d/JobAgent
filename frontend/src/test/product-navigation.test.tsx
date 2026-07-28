import {readFileSync, readdirSync, statSync} from 'node:fs';
import {join, normalize} from 'node:path';
import {fileURLToPath} from 'node:url';
import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {
  SideNav,
  useSideNavCollapse,
} from '@astryxdesign/core/SideNav';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it, vi} from 'vitest';

import type {CvTailoringController} from '../features/cv-tailoring/state';
import {
  createEmptySavedJobsController,
  type SavedJobsController,
} from '../features/jobs/savedJobsState';
import type {SavedJobListItem} from '../features/jobs/types';
import {ProductSidebar} from '../features/navigation/ProductSidebar';
import {PRODUCT_DESTINATIONS} from '../features/navigation/productNavigation';

const sourceRoot = fileURLToPath(new URL('../features', import.meta.url));
const JOB_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';

function job(): SavedJobListItem {
  return {
    id: JOB_ID,
    title: 'Backend Engineer',
    company: 'Acme',
    processing_status: 'processed',
    jd_quality: 'full',
    source_type: 'text',
    source_url: null,
    created_at: '2026-07-28T10:00:00Z',
    updated_at: '2026-07-28T10:00:00Z',
    evaluation_state: 'none',
    latest_score: null,
  };
}

function savedJobsController(selectedJobId: string | null = null): SavedJobsController {
  const base = createEmptySavedJobsController();
  return {
    ...base,
    state: {
      ...base.state,
      selectedJobId,
      list: {
        phase: 'ready',
        data: {items: [job()], next_cursor: null},
        error: null,
        loaded: true,
      },
    },
    selectJob: vi.fn(),
    loadList: vi.fn().mockResolvedValue(undefined),
    loadDetail: vi.fn().mockResolvedValue(undefined),
    invalidateCurrentness: vi.fn(),
  };
}

function tailoringController(): CvTailoringController {
  return {
    state: {
      profileScopeKey: 'profile:ready',
      sessions: {phase: 'idle', data: null, error: null},
      selectedSessionId: null,
      selectedVersionId: null,
      detail: {phase: 'idle', data: null, error: null},
      draft: null,
      draftDirty: false,
      conflict: false,
      stream: {phase: 'idle', data: null, error: null},
    },
    loadSessions: vi.fn().mockResolvedValue(undefined),
    openSession: vi.fn().mockResolvedValue(true),
    createSession: vi.fn().mockResolvedValue(null),
    createAiVersion: vi.fn().mockResolvedValue(false),
    setDraft: vi.fn(),
    saveManualVersion: vi.fn().mockResolvedValue(false),
    selectVersion: vi.fn().mockResolvedValue(false),
    deleteSession: vi.fn().mockResolvedValue(true),
  };
}

function CollapseProbe() {
  const {isCollapsed, setIsCollapsed} = useSideNavCollapse();
  return (
    <button type="button" onClick={() => setIsCollapsed(!isCollapsed)}>
      {isCollapsed ? 'Collapsed' : 'Expanded'}
    </button>
  );
}

function productShell(
  savedJobs: SavedJobsController,
  tailoring: CvTailoringController,
  savedJobsInvalidateKey = 0,
) {
  return (
    <Theme theme={neutralTheme}>
      <SideNav
        collapsible={{hasButton: false}}
        footerIcons={<CollapseProbe />}
      >
        <ProductSidebar
          overview={<span>Overview content</span>}
          savedJobs={savedJobs}
          tailoring={tailoring}
          savedJobsInvalidateKey={savedJobsInvalidateKey}
        />
      </SideNav>
    </Theme>
  );
}

function frontendSourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    return statSync(path).isDirectory()
      ? frontendSourceFiles(path)
      : /\.(?:ts|tsx|css)$/.test(path)
        ? [path]
        : [];
  });
}

describe('product navigation', () => {
  it('defines the three product destinations in their product order', () => {
    expect(PRODUCT_DESTINATIONS.map(({id, label}) => [id, label])).toEqual([
      ['overview', 'Overview'],
      ['saved-jobs', 'Saved Jobs'],
      ['tailored-cvs', 'Tailored CVs'],
    ]);
  });

  it('removes technical observability labels and modules from retained source', () => {
    const source = frontendSourceFiles(sourceRoot)
      .map((file) => readFileSync(file, 'utf8'))
      .join('\n');
    expect(source).not.toContain('LLM chunks');
    expect(source).not.toContain('Neo4j graph');
    expect(source).not.toContain('Agent runs');
    expect(source).not.toContain('features/observability');
  });

  it('keeps saved-job and CV-tailoring controller ownership in App', () => {
    const app = readFileSync(
      fileURLToPath(new URL('../app/App.tsx', import.meta.url)),
      'utf8',
    );
    const controllerDefinitions = new Set(
      [
        fileURLToPath(
          new URL('../features/jobs/savedJobsState.ts', import.meta.url),
        ),
        fileURLToPath(
          new URL('../features/cv-tailoring/state.ts', import.meta.url),
        ),
      ].map(normalize),
    );
    const featureSource = frontendSourceFiles(
      fileURLToPath(new URL('../features', import.meta.url)),
    )
      .filter((file) => !controllerDefinitions.has(normalize(file)))
      .map((file) => readFileSync(file, 'utf8'))
      .join('\n');

    expect(app.split('useSavedJobsState(')).toHaveLength(2);
    expect(app.split('useCvTailoringState(')).toHaveLength(2);
    expect(featureSource).not.toContain('useSavedJobsState(');
    expect(featureSource).not.toContain('useCvTailoringState(');
  });

  it('loads only the selected destination, expands the rail, and loads selected Job detail', async () => {
    const savedJobs = savedJobsController();
    const tailoring = tailoringController();
    render(productShell(savedJobs, tailoring));

    expect(screen.getByText('Overview content')).toBeInTheDocument();
    expect(savedJobs.loadList).not.toHaveBeenCalled();
    expect(tailoring.loadSessions).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', {name: 'Expanded'}));
    expect(screen.getByRole('button', {name: 'Collapsed'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Saved Jobs'}));

    expect(screen.getByRole('button', {name: 'Expanded'})).toBeInTheDocument();
    await waitFor(() => expect(savedJobs.loadList).toHaveBeenCalledTimes(1));
    expect(tailoring.loadSessions).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByTestId(`jobagent-saved-job-select-${JOB_ID}`),
    );
    expect(savedJobs.selectJob).toHaveBeenCalledWith(JOB_ID);
    expect(savedJobs.loadDetail).toHaveBeenCalledWith(JOB_ID);

    await userEvent.click(screen.getByRole('button', {name: 'Tailored CVs'}));
    await waitFor(() => expect(tailoring.loadSessions).toHaveBeenCalledTimes(1));
    expect(savedJobs.loadList).toHaveBeenCalledTimes(1);
  });

  it('refreshes open Saved Jobs after invalidation and keeps closed destinations lazy', async () => {
    const openSavedJobs = savedJobsController(JOB_ID);
    const openTailoring = tailoringController();
    const openView = render(productShell(openSavedJobs, openTailoring));
    await userEvent.click(screen.getByRole('button', {name: 'Saved Jobs'}));
    await waitFor(() => expect(openSavedJobs.loadList).toHaveBeenCalledTimes(1));
    vi.mocked(openSavedJobs.loadList).mockClear();

    openSavedJobs.invalidateCurrentness();
    openView.rerender(productShell(openSavedJobs, openTailoring, 1));
    await waitFor(() => {
      expect(openSavedJobs.invalidateCurrentness).toHaveBeenCalledTimes(1);
      expect(openSavedJobs.loadList).toHaveBeenCalledWith({}, {force: true});
      expect(openSavedJobs.loadDetail).toHaveBeenCalledWith(JOB_ID, {
        force: true,
      });
    });
    openView.unmount();

    const closedSavedJobs = savedJobsController(JOB_ID);
    const closedTailoring = tailoringController();
    const closedView = render(productShell(closedSavedJobs, closedTailoring));
    closedSavedJobs.invalidateCurrentness();
    closedView.rerender(productShell(closedSavedJobs, closedTailoring, 1));
    await waitFor(() =>
      expect(closedSavedJobs.invalidateCurrentness).toHaveBeenCalledTimes(1),
    );
    expect(closedSavedJobs.loadList).not.toHaveBeenCalled();
    expect(closedSavedJobs.loadDetail).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', {name: 'Saved Jobs'}));
    await waitFor(() => {
      expect(closedSavedJobs.loadList).toHaveBeenCalledTimes(1);
      expect(closedSavedJobs.loadList).toHaveBeenCalledWith({}, {force: true});
      expect(closedSavedJobs.loadDetail).toHaveBeenCalledTimes(1);
      expect(closedSavedJobs.loadDetail).toHaveBeenCalledWith(JOB_ID, {
        force: true,
      });
    });
    expect(closedTailoring.loadSessions).not.toHaveBeenCalled();
  });
});

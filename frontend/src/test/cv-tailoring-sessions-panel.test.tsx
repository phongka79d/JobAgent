import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {TailoringSessionsPanel} from '../features/cv-tailoring/TailoringSessionsPanel';
import type {CvTailoringController} from '../features/cv-tailoring/state';
import type {TailoringSessionSummary} from '../features/cv-tailoring/types';

const PROFILE_ID = '11111111-1111-4111-8111-111111111111';
const READY_ID = '22222222-2222-4222-8222-222222222222';
const RUNNING_ID = '33333333-3333-4333-8333-333333333333';
const FAILED_ID = '44444444-4444-4444-8444-444444444444';
const STALE_ID = '55555555-5555-4555-8555-555555555555';
const NOW = '2026-07-26T00:00:00Z';

function summary(
  id: string,
  overrides: Partial<TailoringSessionSummary> = {},
): TailoringSessionSummary {
  return {
    id,
    profile_id: PROFILE_ID,
    job_label: null,
    instruction: 'Điều chỉnh theo yêu cầu sản phẩm',
    template_version: 'latex-cv-v1',
    state: 'ready',
    currentness: 'current',
    latest_version_number: 1,
    error_code: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function controller(
  items: readonly TailoringSessionSummary[],
  overrides: Partial<CvTailoringController> = {},
  stateOverrides: Partial<CvTailoringController['state']> = {},
): CvTailoringController {
  return {
    state: {
      profileScopeKey: `${PROFILE_ID}:ready`,
      sessions: {phase: 'ready', data: {items}, error: null},
      selectedSessionId: READY_ID,
      selectedVersionId: null,
      detail: {phase: 'idle', data: null, error: null},
      draft: null,
      draftDirty: false,
      conflict: false,
      stream: {phase: 'idle', data: null, error: null},
      lastOutcome: null,
      lastOutcomeSource: null,
      ...stateOverrides,
    },
    loadSessions: vi.fn().mockResolvedValue(undefined),
    openSession: vi.fn().mockResolvedValue(true),
    createSession: vi.fn().mockResolvedValue(null),
    createAiVersion: vi.fn().mockResolvedValue(false),
    setDraft: vi.fn(),
    saveManualVersion: vi.fn().mockResolvedValue(false),
    selectVersion: vi.fn().mockResolvedValue(false),
    deleteSession: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
}

function renderPanel(value: CvTailoringController, onOpen = vi.fn()) {
  render(
    <Theme theme={neutralTheme}>
      <TailoringSessionsPanel controller={value} onOpenSession={onOpen} />
    </Theme>,
  );
  return onOpen;
}

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

describe('TailoringSessionsPanel', () => {
  it('renders scoped sessions as rows with safe labels, states, and selection', async () => {
    const value = controller([
      summary(READY_ID, {
        job_label: {title: 'Data Analyst', company: 'Synthetic Co'},
      }),
      summary(RUNNING_ID, {
        state: 'generating',
        latest_version_number: 0,
      }),
      summary(STALE_ID, {currentness: 'stale'}),
      summary(FAILED_ID, {
        state: 'failed',
        latest_version_number: 0,
        error_code: 'TAILORING_GROUNDING_FAILED',
      }),
    ]);
    const onOpen = renderPanel(value);

    await waitFor(() => expect(value.loadSessions).toHaveBeenCalledTimes(1));
    expect(screen.getByText('Data Analyst · Synthetic Co')).toBeInTheDocument();
    expect(screen.getAllByText('Đang tạo').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Dữ liệu cũ').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Thất bại').length).toBeGreaterThan(0);
    expect(screen.queryByText(READY_ID)).not.toBeInTheDocument();
    expect(screen.getByTestId(`jobagent-tailoring-session-${READY_ID}`)).toHaveAttribute(
      'aria-selected',
      'true',
    );

    await userEvent.click(
      screen.getByTestId(`jobagent-tailoring-session-${READY_ID}`),
    );
    expect(onOpen).toHaveBeenCalledWith(READY_ID);
  });

  it('offers explicit retry and confirmed delete for a failed zero-version session', async () => {
    const retry = vi.fn().mockResolvedValue(true);
    const remove = vi.fn().mockResolvedValue(true);
    const value = controller(
      [
        summary(FAILED_ID, {
          state: 'failed',
          latest_version_number: 0,
          error_code: 'TAILORING_GROUNDING_FAILED',
        }),
      ],
      {createAiVersion: retry, deleteSession: remove},
    );
    renderPanel(value);

    await userEvent.click(screen.getByRole('button', {name: 'Thử tạo lại'}));
    expect(retry).toHaveBeenCalledWith(FAILED_ID, {
      parent_version_id: null,
      instruction: '',
      target_section_ids: [],
    });

    await userEvent.click(screen.getByRole('button', {name: 'Xóa phiên CV'}));
    expect(
      screen.getByRole('alertdialog', {name: 'Xóa phiên CV đã chỉnh?'}),
    ).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', {name: 'Xóa phiên'}));
    await waitFor(() => expect(remove).toHaveBeenCalledWith(FAILED_ID));
  });

  it('renders empty and retryable error states without leaking unsafe detail', async () => {
    const emptyController = controller([], {}, {
      sessions: {phase: 'empty', data: {items: []}, error: null},
    });
    renderPanel(emptyController);
    expect(screen.getByText('Chưa có CV đã chỉnh')).toBeInTheDocument();
    cleanup();

    const errorController = controller([], {}, {
      sessions: {
        phase: 'error',
        data: {items: []},
        error: {
          code: 'REQUEST_FAILED',
          summary: String.raw`C:\private\resume.tex \documentclass raw JD candidate@example.test`,
        },
      },
    });
    renderPanel(errorController);
    expect(
      screen.getByText('Không thể tải danh sách CV đã chỉnh.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/private|documentclass|raw JD|candidate@/i),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Thử lại'}));
    expect(errorController.loadSessions).toHaveBeenCalledTimes(2);
  });
});

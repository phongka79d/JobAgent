import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {TailoringEditor} from '../features/cv-tailoring/TailoringEditor';
import type {CvTailoringController} from '../features/cv-tailoring/state';
import type {
  TailoredCVContent,
  TailoringSessionDetailResponse,
} from '../features/cv-tailoring/types';

const PROFILE_ID = '11111111-1111-4111-8111-111111111111';
const SESSION_ID = '22222222-2222-4222-8222-222222222222';
const VERSION_ID = '33333333-3333-4333-8333-333333333333';
const VERSION_2_ID = '44444444-4444-4444-8444-444444444444';
const RUN_ID = '55555555-5555-4555-8555-555555555555';
const NOW = '2026-07-26T00:00:00Z';

function content(): TailoredCVContent {
  return {
    header: {
      full_name: 'Synthetic Candidate',
      location: 'Ha Noi',
      phone: null,
      email: 'candidate@example.test',
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
            id: 'summary-item',
            source_entry_id: 'source-summary',
            title: null,
            subtitle: null,
            date_text: null,
            location: null,
            body: {text: 'Grounded summary', source_fact_ids: ['sf_summary']},
            bullets: [
              {text: 'First grounded bullet', source_fact_ids: ['sf_bullet_1']},
              {text: 'Second grounded bullet', source_fact_ids: ['sf_bullet_2']},
            ],
            attributes: [],
          },
        ],
      },
      {
        id: 'awards',
        ordinal: 1,
        heading: 'Awards',
        kind: 'awards',
        items: [
          {
            id: 'award-item',
            source_entry_id: 'source-award',
            title: {text: 'Synthetic Award', source_fact_ids: ['sf_award']},
            subtitle: null,
            date_text: null,
            location: null,
            body: {text: '', source_fact_ids: []},
            bullets: [],
            attributes: [
              {
                name: 'Category',
                values: [
                  {text: 'Research', source_fact_ids: ['sf_category']},
                ],
              },
            ],
          },
        ],
      },
      {
        id: 'custom',
        ordinal: 2,
        heading: 'Community Work',
        kind: 'other',
        items: [],
      },
    ],
  };
}

function detail(
  currentness: 'current' | 'stale' = 'current',
): TailoringSessionDetailResponse {
  const value = content();
  const firstVersion = {
    id: VERSION_ID,
    version_number: 1,
    parent_version_id: null,
    created_by: 'ai' as const,
    page_count: 1,
    page_warning: null,
    created_at: NOW,
  };
  const secondVersion = {
    id: VERSION_2_ID,
    version_number: 2,
    parent_version_id: VERSION_ID,
    created_by: 'user' as const,
    page_count: 2,
    page_warning: 'CV dài 2 trang',
    created_at: NOW,
  };
  return {
    session: {
      id: SESSION_ID,
      profile_id: PROFILE_ID,
      job_label: {title: 'Data Analyst', company: 'Synthetic Co'},
      instruction: 'Ưu tiên kỹ năng phân tích',
      template_version: 'latex-cv-v1',
      state: 'ready',
      currentness,
      latest_version_number: 2,
      error_code: null,
      created_at: NOW,
      updated_at: NOW,
    },
    versions: [firstVersion, secondVersion],
    selected_version: secondVersion,
    content: value,
    evidence: [
      {
        fact_id: 'sf_summary',
        section_id: 'summary',
        source_entry_id: 'source-summary',
        field_path: 'body',
        source_text: 'Approved source summary',
      },
    ],
    latest_run: {
      id: RUN_ID,
      state: 'completed',
      error_code: null,
      activities: [],
    },
    source_available: true,
    pdf_available: true,
  };
}

function controller(
  currentness: 'current' | 'stale' = 'current',
  overrides: Partial<CvTailoringController> = {},
  stateOverrides: Partial<CvTailoringController['state']> = {},
): CvTailoringController {
  const selected = detail(currentness);
  return {
    state: {
      profileScopeKey: `${PROFILE_ID}:ready`,
      sessions: {phase: 'ready', data: {items: [selected.session]}, error: null},
      selectedSessionId: SESSION_ID,
      selectedVersionId: VERSION_2_ID,
      detail: {phase: 'ready', data: selected, error: null},
      draft: selected.content,
      draftDirty: false,
      conflict: false,
      stream: {phase: 'idle', data: null, error: null},
      lastOutcome: null,
      lastOutcomeSource: null,
      ...stateOverrides,
    },
    loadSessions: vi.fn().mockResolvedValue(undefined),
    openSession: vi.fn().mockResolvedValue(true),
    createSession: vi.fn().mockResolvedValue(SESSION_ID),
    createAiVersion: vi.fn().mockResolvedValue(true),
    setDraft: vi.fn(),
    saveManualVersion: vi.fn().mockResolvedValue(true),
    selectVersion: vi.fn().mockResolvedValue(true),
    deleteSession: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
}

function renderEditor(
  value: CvTailoringController,
  props: Partial<React.ComponentProps<typeof TailoringEditor>> = {},
) {
  render(
    <Theme theme={neutralTheme}>
      <TailoringEditor
        controller={value}
        onBackToChat={vi.fn()}
        onEditProfile={vi.fn()}
        canCreateFresh
        onCreateFresh={vi.fn()}
        onReloadLatest={vi.fn()}
        artifactUrls={{
          source: (versionId) => `/test/versions/${versionId}/source`,
          pdf: (versionId) => `/test/versions/${versionId}/pdf`,
        }}
        {...props}
      />
    </Theme>,
  );
}

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute('open');
  };
});

it('renders the feature-local no-change message without appending a version', () => {
  const value = controller('current', {}, {lastOutcome: 'no_change', lastOutcomeSource: 'manual'});
  renderEditor(value);
  expect(screen.getByText('There are no changes to save.')).toBeInTheDocument();
  expect(value.state.detail.data?.versions).toHaveLength(2);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('TailoringEditor', () => {
  it('renders source order, read-only header, structured fields, evidence, and artifacts', async () => {
    const value = controller('current', {}, {draftDirty: true});
    renderEditor(value);

    const headings = screen
      .getAllByRole('heading', {level: 2})
      .map((node) => node.textContent);
    expect(headings).toEqual(
      expect.arrayContaining(['Summary', 'Awards', 'Community Work']),
    );
    expect(headings.indexOf('Summary')).toBeLessThan(headings.indexOf('Awards'));
    expect(headings.indexOf('Awards')).toBeLessThan(
      headings.indexOf('Community Work'),
    );
    expect(screen.getByLabelText('Họ và tên')).toHaveValue('Synthetic Candidate');
    expect(screen.getByLabelText('Họ và tên')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByLabelText('GitHub')).not.toBeInTheDocument();
    expect(screen.getByText('Category')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Nội dung Summary 1'), {
      target: {value: 'Updated grounded summary'},
    });
    expect(value.setDraft).toHaveBeenCalled();
    const updated = vi.mocked(value.setDraft).mock.calls.at(-1)?.[0];
    expect(updated?.sections[0].items[0].body).toEqual({
      text: 'Updated grounded summary',
      source_fact_ids: ['sf_summary'],
    });

    await userEvent.click(screen.getByText('Nguồn đối chiếu'));
    expect(screen.getByText('Approved source summary')).toBeInTheDocument();
    expect(
      screen.getByTitle('Xem trước PDF CV'),
    ).toHaveAttribute('src', expect.stringContaining(VERSION_2_ID));
    expect(screen.getByRole('link', {name: 'Tải file .tex'})).toHaveAttribute(
      'href',
      expect.stringContaining(`${VERSION_2_ID}/source`),
    );
    expect(screen.getByRole('link', {name: 'Tải PDF'})).toHaveAttribute(
      'href',
      expect.stringContaining(`${VERSION_2_ID}/pdf`),
    );
    expect(screen.getByText('CV dài 2 trang')).toBeInTheDocument();
    expect(screen.getByText('2 trang')).toBeInTheDocument();
  });

  it('saves once and sends an AI request for exactly one selected section', async () => {
    const value = controller('current', {}, {draftDirty: true});
    renderEditor(value);

    fireEvent.click(screen.getByRole('button', {name: 'Lưu version & tạo PDF'}));
    fireEvent.click(screen.getByRole('button', {name: 'Lưu version & tạo PDF'}));
    await waitFor(() => expect(value.saveManualVersion).toHaveBeenCalledTimes(1));

    await userEvent.click(
      screen.getAllByRole('button', {name: 'Nhờ AI chỉnh section này'})[0],
    );
    expect(screen.getByRole('heading', {name: 'Nhờ AI chỉnh Summary'})).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText('Yêu cầu chỉnh sửa'),
      'Nhấn mạnh kết quả phân tích',
    );
    await userEvent.click(screen.getByRole('button', {name: 'Gửi cho AI'}));
    await waitFor(() =>
      expect(value.createAiVersion).toHaveBeenCalledWith(SESSION_ID, {
        parent_version_id: VERSION_2_ID,
        instruction: 'Nhấn mạnh kết quả phân tích',
        target_section_ids: ['summary'],
      }),
    );
  });

  it('requires confirmation before version discard and exposes stale recovery', async () => {
    const value = controller('stale', {}, {draftDirty: true});
    const onCreateFresh = vi.fn();
    renderEditor(value, {onCreateFresh});

    expect(screen.getByText('Dữ liệu nguồn đã thay đổi')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Lưu version & tạo PDF'})).toBeDisabled();
    await userEvent.click(
      screen.getByRole('button', {name: 'Tạo phiên mới từ dữ liệu hiện tại'}),
    );
    expect(onCreateFresh).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByLabelText('Version CV'));
    await userEvent.click(screen.getByText('Version 1 · AI'));
    expect(value.selectVersion).not.toHaveBeenCalled();
    expect(
      screen.getByRole('alertdialog', {name: 'Bỏ thay đổi chưa lưu?'}),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Bỏ thay đổi'}));
    await waitFor(() =>
      expect(value.selectVersion).toHaveBeenCalledWith(VERSION_ID, true),
    );
  });

  it('delegates conflict reload without discarding the local draft', async () => {
    const selected = detail('current');
    const value = controller(
      'current',
      {},
      {
        draft: selected.content,
        draftDirty: true,
        conflict: true,
        detail: {
          phase: 'error',
          data: selected,
          error: {
            code: 'TAILORING_PARENT_CONFLICT',
            summary: 'unsafe detail must not render',
          },
        },
      },
    );
    const onReloadLatest = vi.fn();
    renderEditor(value, {onReloadLatest});

    await userEvent.click(
      screen.getByRole('button', {name: 'Tải version mới nhất'}),
    );

    expect(onReloadLatest).toHaveBeenCalledTimes(1);
    expect(value.openSession).not.toHaveBeenCalled();
    expect(value.state.draft).toBe(selected.content);
    expect(value.state.draftDirty).toBe(true);
  });
});

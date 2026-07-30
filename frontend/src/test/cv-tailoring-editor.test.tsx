import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
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
    page_warning: 'This tailored CV is 2 pages long.',
    created_at: NOW,
  };
  return {
    session: {
      id: SESSION_ID,
      profile_id: PROFILE_ID,
      job_label: {title: 'Data Analyst', company: 'Synthetic Co', display_label: 'Data Analyst · Synthetic Co'},
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
      issues: [],
    },
    fit_warning: null,
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
      pendingFocus: null,
      retryRequest: null,
      ...stateOverrides,
    },
    loadSessions: vi.fn().mockResolvedValue(undefined),
    openSession: vi.fn().mockResolvedValue(true),
    createSession: vi.fn().mockResolvedValue(SESSION_ID),
    createAiVersion: vi.fn().mockResolvedValue(true),
    setDraft: vi.fn(),
    undoIssue: vi.fn(),
    focusIssue: vi.fn(),
    retryIssue: vi.fn(),
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

it('renders the selected version date in English and singular page copy', () => {
  const selected = detail();
  const firstVersion = selected.versions[0];
  if (!firstVersion) throw new Error('Expected the Version 1 fixture');
  const value = controller('current', {}, {
    selectedVersionId: firstVersion.id,
    detail: {
      phase: 'ready',
      data: {...selected, selected_version: firstVersion},
      error: null,
    },
  });

  renderEditor(value);

  expect(
    screen.getByText(
      new Intl.DateTimeFormat('en-CA', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(new Date(firstVersion.created_at)),
    ),
  ).toBeInTheDocument();
  expect(screen.getByText('1 page')).toBeInTheDocument();
});

it('binds safe issues to fields and exposes source, undo, and retry actions', async () => {
  const issue = {section_id: 'summary', section_heading: 'Summary', item_index: 0, field: 'body' as const, reason: 'not_in_source' as const};
  const focusIssue = vi.fn();
  const undoIssue = vi.fn();
  const retryIssue = vi.fn();
  const createAiVersion = vi.fn();
  const value = controller('current', {focusIssue, undoIssue, retryIssue, createAiVersion}, {stream: {phase: 'error', data: null, error: {code: 'TAILORING_GROUNDING_FAILED', summary: 'Not source-supported', issues: [issue]}}});
  renderEditor(value);
  expect(screen.getByText('Source support warning')).toBeInTheDocument();
  expect(
    screen.getByText(
      'Manual edits are still available. Use source evidence, undo the flagged field, or retry with AI.',
    ),
  ).toBeInTheDocument();
  expect(screen.getByText('Summary: This value is not supported by the selected source.')).toHaveAttribute('id', 'tailoring-issue-summary-0-body-not_in_source');
  const groundedField = screen.getByRole('textbox', {name: 'Summary body'});
  expect(groundedField).toHaveAttribute('aria-invalid', 'true');
  expect(groundedField).toHaveAccessibleDescription(
    /Needs attention: This value is not supported by the selected source\./,
  );
  await userEvent.click(screen.getByRole('button', {name: 'View source'}));
  const sourceEvidence = await screen.findByRole('region', {
    name: 'Summary source evidence',
  });
  await waitFor(() => expect(sourceEvidence).toHaveFocus());
  await userEvent.click(screen.getByRole('button', {name: 'Focus field'}));
  await userEvent.click(screen.getByRole('button', {name: 'Undo change'}));
  await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
  expect(focusIssue).toHaveBeenCalledWith(issue);
  expect(undoIssue).toHaveBeenCalledWith(issue);
  expect(retryIssue).toHaveBeenCalledWith(issue);
  expect(createAiVersion).not.toHaveBeenCalled();
});

it('renders base-to-tailored version lineage', () => {
  const value = controller('current');
  renderEditor(value);

  const lineage = screen.getByRole('tree', {name: 'Version lineage'});
  expect(
    within(lineage).getByRole('treeitem', {name: 'Base CV'}),
  ).toBeInTheDocument();
  expect(
    within(lineage).getByRole('treeitem', {name: 'Version 1 - AI'}),
  ).toBeInTheDocument();
  expect(
    within(lineage).getByRole('treeitem', {name: 'Version 2 - You'}),
  ).toBeInTheDocument();
});

it('renders a non-blocking JD fit warning from the selected version detail', () => {
  const selected = detail('current');
  const value = controller('current', {}, {
    detail: {
      phase: 'ready',
      data: {
        ...selected,
        fit_warning: 'This version mentions fewer required JD skills than its parent: SQL.',
      },
      error: null,
    },
  });
  renderEditor(value);

  expect(screen.getByText('JD fit warning')).toBeInTheDocument();
  expect(
    screen.getByText(
      'This version mentions fewer required JD skills than its parent: SQL.',
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', {name: 'Save version'})).toBeInTheDocument();
});

it('focuses source evidence only after the disclosure is open', async () => {
  const nativeFocus = HTMLElement.prototype.focus;
  vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function focus(
    this: HTMLElement,
  ) {
    if (this.getAttribute('role') === 'region') {
      const trigger = this.parentElement?.parentElement?.querySelector(
        ':scope > button[aria-expanded]',
      );
      if (trigger?.getAttribute('aria-expanded') === 'false') return;
    }
    nativeFocus.call(this);
  });
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  const issue = {
    section_id: 'summary',
    section_heading: 'Summary',
    item_index: 0,
    field: 'body' as const,
    reason: 'not_in_source' as const,
  };
  const value = controller('current', {}, {
    stream: {
      phase: 'error',
      data: null,
      error: {
        code: 'TAILORING_GROUNDING_FAILED',
        summary: 'Not source-supported',
        issues: [issue],
      },
    },
  });

  renderEditor(value);
  await userEvent.click(screen.getByRole('button', {name: 'View source'}));

  expect(
    await screen.findByRole('region', {name: 'Summary source evidence'}),
  ).toHaveFocus();
});

it('focuses the section container for a section-level grounding issue', async () => {
  const issue = {
    section_id: 'summary',
    section_heading: 'Summary',
    item_index: null,
    field: 'section' as const,
    reason: 'structure_changed' as const,
  };
  const value = controller('current', {}, {
    pendingFocus: {key: 1, issue},
  });

  renderEditor(value);

  await waitFor(() => {
    expect(
      screen.getByTestId('jobagent-tailored-section-summary'),
    ).toHaveFocus();
  });
});

it('focuses the exact input for an item-level grounding issue', async () => {
  const issue = {
    section_id: 'summary',
    section_heading: 'Summary',
    item_index: 0,
    field: 'body' as const,
    reason: 'not_in_source' as const,
  };
  const value = controller('current', {}, {
    pendingFocus: {key: 1, issue},
  });

  renderEditor(value);

  await waitFor(() => {
    expect(
      screen.getByRole('textbox', {name: 'Summary body'}),
    ).toHaveFocus();
  });
});

it('uses a new tab only for preview and keeps download failures in the editor', async () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', {status: 503})));
  renderEditor(controller());
  await userEvent.click(screen.getByRole('button', {name: 'Preview PDF'}));
  expect(open).toHaveBeenCalledWith(expect.stringContaining('/pdf'), '_blank', 'noopener,noreferrer');
  await userEvent.click(screen.getByRole('button', {name: 'Download PDF'}));
  expect(await screen.findByText('The PDF could not be downloaded.')).toBeInTheDocument();
  expect(screen.getByRole('heading', {level: 1, name: 'Tailored CV'})).toBeInTheDocument();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
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
    expect(screen.getByLabelText('Full name')).toHaveValue('Synthetic Candidate');
    expect(screen.getByLabelText('Full name')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByLabelText('GitHub')).not.toBeInTheDocument();
    expect(screen.getByText('Category')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Body Summary 1'), {
      target: {value: 'Updated grounded summary'},
    });
    expect(value.setDraft).toHaveBeenCalled();
    const updated = vi.mocked(value.setDraft).mock.calls.at(-1)?.[0];
    expect(updated?.sections[0].items[0].body).toEqual({
      text: 'Updated grounded summary',
      source_fact_ids: ['sf_summary'],
    });

    await userEvent.click(screen.getByText('Source evidence'));
    expect(screen.getByText('Approved source summary')).toBeInTheDocument();
    expect(
      screen.getByTitle('Tailored CV PDF preview'),
    ).toHaveAttribute('src', expect.stringContaining(VERSION_2_ID));
    expect(screen.getByText('2 pages')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Preview PDF'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Download PDF'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Advanced'}));
    expect(screen.getByRole('button', {name: 'Download LaTeX source'})).toBeInTheDocument();
    expect(screen.getByText('This tailored CV is 2 pages long.')).toBeInTheDocument();
    expect(document.querySelectorAll('[data-scroll-owner="viewport"]')).toHaveLength(2);
  });

  it('saves once and sends an AI request for exactly one selected section', async () => {
    const value = controller('current', {}, {draftDirty: true});
    renderEditor(value);

    fireEvent.click(screen.getByRole('button', {name: 'Save version'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save version'}));
    await waitFor(() => expect(value.saveManualVersion).toHaveBeenCalledTimes(1));

    await userEvent.click(
      screen.getAllByRole('button', {name: 'Ask AI to revise this section'})[0],
    );
    expect(screen.getByRole('heading', {name: 'Ask AI to revise Summary'})).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText('Revision request'),
      'Nhấn mạnh kết quả phân tích',
    );
    await userEvent.click(screen.getByRole('button', {name: 'Send to AI'}));
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

    expect(screen.getByText('Source data changed')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Save version'})).toBeDisabled();
    await userEvent.click(
      screen.getByRole('button', {name: 'Create a new session from current data'}),
    );
    expect(onCreateFresh).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByLabelText('Version CV'));
    await userEvent.click(screen.getByText('Version 1 · AI'));
    expect(value.selectVersion).not.toHaveBeenCalled();
    expect(
      screen.getByRole('alertdialog', {name: 'Discard unsaved changes?'}),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Discard changes'}));
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
      screen.getByRole('button', {name: 'Load latest version'}),
    );

    expect(onReloadLatest).toHaveBeenCalledTimes(1);
    expect(value.openSession).not.toHaveBeenCalled();
    expect(value.state.draft).toBe(selected.content);
    expect(value.state.draftDirty).toBe(true);
  });
});

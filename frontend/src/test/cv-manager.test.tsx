/**
 * CV Manager panel/dialog interaction tests (Plan 9 / 07B).
 */

import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeAll, beforeEach, describe, expect, it, vi} from 'vitest';
import type {ComponentProps} from 'react';

import type {ObservabilityApi} from '../features/observability/api';
import {CV_DELETE_SCOPE_WARNING} from '../features/observability/CvDeleteDialog';
import {
  canDeleteCv,
  CvManagerPanel,
} from '../features/observability/CvManagerPanel';
import {toGraphModel} from '../features/observability/graphPresentation';
import type {CvHistoryItem} from '../features/observability/types';
import {CvSidebar} from '../features/profile/CvSidebar';
import type {ProfileReadResponse} from '../features/profile/types';
import {
  ACTIVE_ATTACHMENT_ID,
  ATTACHMENT_ID,
  cvManagerHistoryPage,
  graphWithCvBranch,
  installMatchMedia,
  mockObservabilityApi,
  renderObservabilitySidebar,
} from './support/observability';

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

beforeEach(() => {
  installMatchMedia(false);
});

function activeItem(): CvHistoryItem {
  return cvManagerHistoryPage().items[0]!;
}

function archivedItem(): CvHistoryItem {
  return cvManagerHistoryPage().items[1]!;
}

function renderPanel(
  overrides: Partial<ComponentProps<typeof CvManagerPanel>> = {},
) {
  const page = cvManagerHistoryPage();
  const props: ComponentProps<typeof CvManagerPanel> = {
    resource: {
      phase: 'ready',
      data: page,
      error: null,
      loaded: true,
    },
    selectedAttachmentId: ATTACHMENT_ID,
    pendingByAttachment: {},
    errorsByAttachment: {},
    onSelect: vi.fn(),
    onOpenFile: vi.fn(),
    onRefresh: vi.fn(),
    onReprocess: vi.fn(),
    onConfirmDelete: vi.fn().mockResolvedValue('success'),
    onClearError: vi.fn(),
    ...overrides,
  };
  return {
    props,
    ...render(
      <Theme theme={neutralTheme}>
        <CvManagerPanel {...props} />
      </Theme>,
    ),
  };
}

function CvSidebarWithReprocess({
  api,
  loadProfile,
  onCvReprocess,
}: {
  api: ObservabilityApi;
  loadProfile: () => Promise<ProfileReadResponse>;
  onCvReprocess: (id: string) => boolean;
}) {
  return (
    <CvSidebar
      isUploadDisabled={false}
      onSidebarUploadSuccess={vi.fn()}
      onCvReprocess={onCvReprocess}
      deps={{
        loadProfile,
        uploadCv: vi.fn(),
        observability: api,
      }}
    />
  );
}

describe('canDeleteCv guard', () => {
  it('forbids delete for active and allows non-active states', () => {
    expect(canDeleteCv(activeItem())).toBe(false);
    expect(canDeleteCv(archivedItem())).toBe(true);
    expect(canDeleteCv({...archivedItem(), state: 'failed'})).toBe(true);
    expect(canDeleteCv({...archivedItem(), state: 'staged'})).toBe(true);
  });
});

describe('CV Manager activation loading presentation', () => {
  it('retains prior rows while phase is loading (not header-only idle)', () => {
    const page = cvManagerHistoryPage();
    renderPanel({
      resource: {
        phase: 'loading',
        data: page,
        error: null,
        loaded: false,
      },
      selectedAttachmentId: ATTACHMENT_ID,
    });

    expect(screen.getByTestId('jobagent-obs-cv-history')).toBeInTheDocument();
    expect(screen.getByText('active.pdf')).toBeInTheDocument();
    expect(screen.getByText('archived.pdf')).toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-obs-cv-history-empty'),
    ).not.toBeInTheDocument();
    // Loading without data would show skeleton; with retained data, rows stay.
    expect(
      screen.queryByTestId('jobagent-obs-cv-history-loading'),
    ).not.toBeInTheDocument();
  });

  it('shows established skeleton when loading with no retained rows', () => {
    renderPanel({
      resource: {
        phase: 'loading',
        data: null,
        error: null,
        loaded: false,
      },
      selectedAttachmentId: null,
    });

    expect(
      screen.getByTestId('jobagent-obs-cv-history-loading'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('jobagent-obs-cv-history-empty'),
    ).not.toBeInTheDocument();
  });
});

describe('CV Manager panel actions', () => {
  it('shows one Active badge and only Open/Re-extract for the active row', () => {
    renderPanel({selectedAttachmentId: ACTIVE_ATTACHMENT_ID});

    expect(
      screen.getByTestId(`jobagent-obs-cv-active-badge-${ACTIVE_ATTACHMENT_ID}`),
    ).toHaveTextContent('Active');
    expect(
      screen.queryAllByTestId(`jobagent-obs-cv-active-badge-${ATTACHMENT_ID}`),
    ).toHaveLength(0);

    const actions = screen.getByTestId(
      `jobagent-obs-cv-actions-${ACTIVE_ATTACHMENT_ID}`,
    );
    expect(
      within(actions).getByTestId(
        `jobagent-obs-cv-open-${ACTIVE_ATTACHMENT_ID}`,
      ),
    ).toBeEnabled();
    expect(
      within(actions).getByTestId(
        `jobagent-obs-cv-reextract-${ACTIVE_ATTACHMENT_ID}`,
      ),
    ).toBeEnabled();
    expect(
      within(actions).queryByTestId(
        `jobagent-obs-cv-delete-${ACTIVE_ATTACHMENT_ID}`,
      ),
    ).toBeNull();
    expect(
      within(actions).queryByTestId(
        `jobagent-obs-cv-make-active-${ACTIVE_ATTACHMENT_ID}`,
      ),
    ).toBeNull();
  });

  it('exposes Open, Make active, and Delete for archived selection', () => {
    renderPanel({selectedAttachmentId: ATTACHMENT_ID});

    const actions = screen.getByTestId(
      `jobagent-obs-cv-actions-${ATTACHMENT_ID}`,
    );
    expect(
      within(actions).getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`),
    ).toBeEnabled();
    expect(
      within(actions).getByTestId(
        `jobagent-obs-cv-make-active-${ATTACHMENT_ID}`,
      ),
    ).toBeEnabled();
    expect(
      within(actions).getByTestId(`jobagent-obs-cv-delete-${ATTACHMENT_ID}`),
    ).toBeEnabled();
    expect(
      within(actions).queryByTestId(
        `jobagent-obs-cv-reextract-${ATTACHMENT_ID}`,
      ),
    ).toBeNull();
  });

  it('disables row actions while a pending action is in flight', () => {
    renderPanel({
      selectedAttachmentId: ATTACHMENT_ID,
      pendingByAttachment: {[ATTACHMENT_ID]: 'reprocess'},
    });

    const actions = screen.getByTestId(
      `jobagent-obs-cv-actions-${ATTACHMENT_ID}`,
    );
    expect(
      within(actions).getByTestId(`jobagent-obs-cv-open-${ATTACHMENT_ID}`),
    ).toBeDisabled();
    expect(
      within(actions).getByTestId(
        `jobagent-obs-cv-make-active-${ATTACHMENT_ID}`,
      ),
    ).toBeDisabled();
    expect(
      within(actions).getByTestId(`jobagent-obs-cv-delete-${ATTACHMENT_ID}`),
    ).toBeDisabled();
  });

  it('names the file and scope in the accessible delete confirmation', async () => {
    const user = userEvent.setup();
    const onConfirmDelete = vi.fn().mockResolvedValue('success' as const);
    renderPanel({onConfirmDelete});

    await user.click(
      screen.getByTestId(`jobagent-obs-cv-delete-${ATTACHMENT_ID}`),
    );

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('archived.pdf');
    expect(dialog).toHaveTextContent(CV_DELETE_SCOPE_WARNING);
    expect(
      within(dialog).getByRole('button', {name: 'Delete CV'}),
    ).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', {name: 'Delete CV'}));
    await waitFor(() => {
      expect(onConfirmDelete).toHaveBeenCalledTimes(1);
    });
    expect(onConfirmDelete.mock.calls[0]?.[0].id).toBe(ATTACHMENT_ID);
  });

  it('keeps the row and recovery message after partial delete failure', async () => {
    const user = userEvent.setup();
    const onConfirmDelete = vi.fn().mockResolvedValue('error' as const);
    const {rerender, props} = renderPanel({onConfirmDelete});

    await user.click(
      screen.getByTestId(`jobagent-obs-cv-delete-${ATTACHMENT_ID}`),
    );
    await user.click(await screen.findByRole('button', {name: 'Delete CV'}));
    await waitFor(() => {
      expect(onConfirmDelete).toHaveBeenCalled();
    });

    rerender(
      <Theme theme={neutralTheme}>
        <CvManagerPanel
          {...props}
          onConfirmDelete={onConfirmDelete}
          errorsByAttachment={{
            [ATTACHMENT_ID]: {
              code: 'CV_DELETE_GRAPH_FAILED',
              summary:
                'CV deletion is incomplete; the attachment remains in deleting state. Retry DELETE for the same attachment id.',
            },
          }}
        />
      </Theme>,
    );

    expect(
      screen.getByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    ).toBeInTheDocument();
    const banner = screen.getByTestId(
      `jobagent-obs-cv-action-error-${ATTACHMENT_ID}`,
    );
    expect(banner).toHaveTextContent('CV_DELETE_GRAPH_FAILED');
    expect(banner).toHaveTextContent('Retry DELETE');
    expect(
      screen.getByTestId(`jobagent-obs-cv-delete-${ATTACHMENT_ID}`),
    ).toBeEnabled();
  });

  it('invokes reprocess for Re-extract without changing Active badge', async () => {
    const user = userEvent.setup();
    const onReprocess = vi.fn();
    renderPanel({
      selectedAttachmentId: ACTIVE_ATTACHMENT_ID,
      onReprocess,
    });

    expect(
      screen.getByTestId(`jobagent-obs-cv-active-badge-${ACTIVE_ATTACHMENT_ID}`),
    ).toBeInTheDocument();

    await user.click(
      screen.getByTestId(`jobagent-obs-cv-reextract-${ACTIVE_ATTACHMENT_ID}`),
    );
    expect(onReprocess).toHaveBeenCalledWith(
      expect.objectContaining({id: ACTIVE_ATTACHMENT_ID, state: 'active'}),
    );
    expect(
      screen.getByTestId(`jobagent-obs-cv-active-badge-${ACTIVE_ATTACHMENT_ID}`),
    ).toBeInTheDocument();
  });
});

describe('CV Manager sidebar integration', () => {
  it('renames the tab/panel to CV Manager and wires delete through confirmDelete', async () => {
    const user = userEvent.setup();
    const deleteCv = vi.fn().mockResolvedValue(undefined);
    const api = mockObservabilityApi({
      fetchCvHistory: vi.fn().mockResolvedValue(cvManagerHistoryPage()),
      deleteCv,
    });
    renderObservabilitySidebar(api);

    await user.click(screen.getByRole('tab', {name: 'CV Manager'}));
    const panel = await screen.findByTestId('jobagent-obs-cv-history');
    expect(panel).toBeInTheDocument();
    expect(
      within(panel).getByRole('list', {name: 'CV Manager'}),
    ).toBeInTheDocument();

    await user.click(
      await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await user.click(
      screen.getByTestId(`jobagent-obs-cv-delete-${ATTACHMENT_ID}`),
    );
    await user.click(await screen.findByRole('button', {name: 'Delete CV'}));

    await waitFor(() => {
      expect(deleteCv).toHaveBeenCalledWith(ATTACHMENT_ID, undefined);
    });
    await waitFor(() => {
      expect(
        screen.queryByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
      ).toBeNull();
    });
    expect(
      screen.getByTestId(`jobagent-obs-cv-select-${ACTIVE_ATTACHMENT_ID}`),
    ).toBeInTheDocument();
  });

  it('calls onCvReprocess when Make active is chosen on an archived CV', async () => {
    const user = userEvent.setup();
    const onCvReprocess = vi.fn().mockReturnValue(true);
    const api = mockObservabilityApi({
      fetchCvHistory: vi.fn().mockResolvedValue(cvManagerHistoryPage()),
    });
    const loadProfile = vi.fn().mockResolvedValue({
      present: true,
      profile: {summary: 'ok', current_title: 'Engineer'},
      preferences: null,
      active_attachment: {
        id: ACTIVE_ATTACHMENT_ID,
        original_name: 'active.pdf',
        mime_type: 'application/pdf',
        size_bytes: 1000,
        page_count: 2,
        state: 'active',
        failure_code: null,
      },
      draft_present: false,
      pending_attachment: null,
    } satisfies ProfileReadResponse);

    render(
      <Theme theme={neutralTheme}>
        <CvSidebarWithReprocess
          api={api}
          loadProfile={loadProfile}
          onCvReprocess={onCvReprocess}
        />
      </Theme>,
    );

    await user.click(await screen.findByRole('tab', {name: 'CV Manager'}));
    await user.click(
      await screen.findByTestId(`jobagent-obs-cv-select-${ATTACHMENT_ID}`),
    );
    await user.click(
      screen.getByTestId(`jobagent-obs-cv-make-active-${ATTACHMENT_ID}`),
    );

    expect(onCvReprocess).toHaveBeenCalledWith(ATTACHMENT_ID);
  });
});

describe('graph CV branch mapping', () => {
  it('maps fixed CV/section/entry nodes and structural edges', () => {
    const model = toGraphModel(graphWithCvBranch());
    expect(model.nodes.map((node) => node.key)).toEqual(
      expect.arrayContaining([
        'candidate:cand-1',
        `cv:${ATTACHMENT_ID}`,
        'cv_section:sec-1',
        'cv_entry:ent-1',
        'job:job-1',
        'skill:python',
      ]),
    );
    expect(model.nodes.find((n) => n.kind === 'cv')?.label).toBe('active.pdf');
    expect(model.links.map((link) => link.type)).toEqual(
      expect.arrayContaining([
        'HAS_SKILL',
        'PROJECTS_TO',
        'HAS_SECTION',
        'HAS_ENTRY',
      ]),
    );
    expect(
      model.links.find((link) => link.type === 'PROJECTS_TO'),
    ).toMatchObject({
      source: 'candidate:cand-1',
      target: `cv:${ATTACHMENT_ID}`,
    });
  });
});

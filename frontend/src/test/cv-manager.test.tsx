import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {CvManagerDrawer} from '../features/cv-manager/CvManagerDrawer';
import type {CvManagerApi} from '../features/cv-manager/api';
import {useCvManagerState} from '../features/cv-manager/state';
import type {CvManagerItem, ProfileReextractReview} from '../features/cv-manager/types';
import {ProfileDeleteDialog} from '../features/profile/ProfileDeleteDialog';
import type {ProfileListItem} from '../features/profile/conversationTypes';
import savedJobsStateSource from '../features/jobs/savedJobsState.ts?raw';

const PROFILE_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const ACTIVE_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const FAILED_UNOWNED_ID = '11111111-2222-4333-8444-555555555555';
const OTHER_PROFILE_ID = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
const TS = '2026-07-13T12:00:00.000Z';

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

function activeItem(): CvManagerItem {
  return {
    id: ACTIVE_ID,
    original_name: 'resume.pdf',
    state: 'active',
    failure_code: null,
    page_count: 4,
    file_available: true,
    profile_id: PROFILE_ID,
    profile_display_name: 'Profile A',
    profile_state: 'ready',
    is_active_profile: true,
    allowed_actions: ['preview', 'download', 'reextract'],
    created_at: TS,
    updated_at: TS,
  };
}

function unownedFailedItem(): CvManagerItem {
  return {
    id: FAILED_UNOWNED_ID,
    original_name: 'failed-upload.pdf',
    state: 'failed',
    failure_code: 'EXTRACTION_FAILED',
    page_count: null,
    file_available: false,
    profile_id: null,
    profile_display_name: null,
    profile_state: null,
    is_active_profile: false,
    allowed_actions: ['delete_cv'],
    created_at: TS,
    updated_at: TS,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return {promise, resolve, reject};
}

function StateHarness({
  api,
  profileId = PROFILE_ID,
  profileReady = true,
}: {
  api: CvManagerApi;
  profileId?: string;
  profileReady?: boolean;
}) {
  const controller = useCvManagerState({
    api,
    profileId,
    profileReady,
  });

  return (
    <>
      <button type="button" onClick={() => void controller.open()}>
        Open manager
      </button>
      <button type="button" onClick={() => void controller.refresh()}>
        Force refresh
      </button>
      <button
        type="button"
        onClick={() => void controller.confirmDelete(FAILED_UNOWNED_ID)}
      >
        Confirm delete
      </button>
      <button type="button" onClick={() => void controller.startReextract(profileId ?? PROFILE_ID)}>
        Start re-extract
      </button>
      <output data-testid="controller-state">
        {JSON.stringify(controller.state)}
      </output>
    </>
  );
}

function reviewFixture(revision = TS): ProfileReextractReview {
  return {
    profile_id: PROFILE_ID, revision,
    current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Approved', current_title: 'Engineer', skill_labels: []},
    proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Proposed', current_title: 'Senior Engineer', skill_labels: []},
    changed_fields: [], preference_changes: [], skills_added: [], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: true, can_discard: true,
  };
}

function drawerController(
  overrides: Record<string, unknown> = {},
) {
  const item = unownedFailedItem();
  return {
    state: {
      phase: 'ready' as const,
      items: [item],
      selectedId: item.id,
      pendingByAttachment: {},
      errorsByAttachment: {},
      deleteTargetId: null,
    },
    refresh: vi.fn(),
    select: vi.fn(),
    openDeleteDialog: vi.fn(),
    closeDeleteDialog: vi.fn(),
    confirmDelete: vi.fn().mockResolvedValue(true),
    startReextract: vi.fn().mockResolvedValue(true),
    loadReview: vi.fn().mockResolvedValue(true),
    approveReview: vi.fn().mockResolvedValue(true),
    discardReview: vi.fn().mockResolvedValue(true),
    closeReview: vi.fn(),
    ...overrides,
  };
}

describe('useCvManagerState refresh and scope guards', () => {
  it('forwards an actual AbortSignal and aborts the in-flight scope request', async () => {
    const list = deferred<{items: CvManagerItem[]}>();
    let receivedSignal: AbortSignal | undefined;
    const api: CvManagerApi = {
      fetchCvManager: vi.fn((_signal?: AbortSignal) => {
        receivedSignal = _signal;
        return list.promise;
      }),
      deleteCv: vi.fn(),
    };
    const view = render(<StateHarness api={api} profileId={PROFILE_ID} />);

    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    expect(receivedSignal).toBeInstanceOf(AbortSignal);
    expect(receivedSignal?.aborted).toBe(false);

    view.rerender(<StateHarness api={api} profileId={OTHER_PROFILE_ID} />);
    expect(receivedSignal?.aborted).toBe(true);

    list.resolve({items: []});
  });

  it('preserves prior rows while exposing error after refresh failure', async () => {
    const api: CvManagerApi = {
      fetchCvManager: vi
        .fn()
        .mockResolvedValueOnce({items: [activeItem()]})
        .mockRejectedValueOnce(new Error('private transport detail')),
      deleteCv: vi.fn(),
    };

    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await waitFor(() =>
      expect(screen.getByTestId('controller-state')).toHaveTextContent(
        'resume.pdf',
      ),
    );

    await userEvent.click(
      screen.getByRole('button', {name: 'Force refresh'}),
    );
    await waitFor(() => {
      const state = screen.getByTestId('controller-state');
      expect(state).toHaveTextContent('"phase":"error"');
      expect(state).toHaveTextContent('resume.pdf');
      expect(state).not.toHaveTextContent('private transport detail');
    });
  });

  it('clears data, selection, pending work, and errors on scope change', async () => {
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockResolvedValue({items: [activeItem()]}),
      deleteCv: vi.fn(),
    };
    const view = render(
      <StateHarness api={api} profileId={PROFILE_ID} />,
    );

    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await waitFor(() =>
      expect(screen.getByTestId('controller-state')).toHaveTextContent(
        'resume.pdf',
      ),
    );

    view.rerender(
      <StateHarness api={api} profileId={OTHER_PROFILE_ID} />,
    );
    await waitFor(() => {
      const state = screen.getByTestId('controller-state');
      expect(state).not.toHaveTextContent('resume.pdf');
      expect(state).toHaveTextContent('"selectedId":null');
      expect(state).toHaveTextContent('"pendingByAttachment":{}');
      expect(state).toHaveTextContent('"errorsByAttachment":{}');
    });
  });

  it('ignores a stale list completion after scope change', async () => {
    const list = deferred<{items: CvManagerItem[]}>();
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockReturnValue(list.promise),
      deleteCv: vi.fn(),
    };
    const view = render(
      <StateHarness api={api} profileId={PROFILE_ID} />,
    );

    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    view.rerender(
      <StateHarness api={api} profileId={OTHER_PROFILE_ID} />,
    );

    await act(async () => {
      list.resolve({items: [activeItem()]});
      await Promise.resolve();
    });

    await waitFor(() => {
      const state = screen.getByTestId('controller-state');
      expect(state).not.toHaveTextContent('resume.pdf');
      expect(state).toHaveTextContent('"items":[]');
    });
  });
});

describe('useCvManagerState direct re-extract recovery', () => {
  it('loads the durable server-permitted review after draft_available failure', async () => {
    const getProfileReextractReview = vi.fn().mockResolvedValue(reviewFixture());
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractReview,
      streamProfileReextract: vi.fn(async (_profileId, handlers) => {
        handlers.onEvent({event_id: '11111111-1111-4111-8111-111111111111', operation_id: '22222222-2222-4222-8222-222222222222', profile_id: PROFILE_ID, timestamp: TS, event: 'reextract_failed', payload: {code: 'PROVIDER_FAILED', summary: 'Retry later', draft_available: true}});
      }),
    };
    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Start re-extract'}));
    await waitFor(() => expect(getProfileReextractReview).toHaveBeenCalledWith(PROFILE_ID, expect.any(AbortSignal)));
    expect(screen.getByTestId('controller-state')).toHaveTextContent('"phase":"review"');
    expect(screen.getByTestId('controller-state')).toHaveTextContent('PROVIDER_FAILED');
  });

  it('tries durable review recovery after a stream ends without a terminal event', async () => {
    const getProfileReextractReview = vi.fn().mockResolvedValue(reviewFixture());
    const api: CvManagerApi = {fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractReview, streamProfileReextract: vi.fn().mockResolvedValue(undefined)};
    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Start re-extract'}));
    await waitFor(() => expect(getProfileReextractReview).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('controller-state')).toHaveTextContent('"phase":"review"');
  });

  it('rejects a durable review whose revision does not match review_ready', async () => {
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractReview: vi.fn().mockResolvedValue(reviewFixture('2026-07-29T10:00:00Z')),
      streamProfileReextract: vi.fn(async (_profileId, handlers) => handlers.onEvent({event_id: '11111111-1111-4111-8111-111111111111', operation_id: '22222222-2222-4222-8222-222222222222', profile_id: PROFILE_ID, timestamp: TS, event: 'reextract_review_ready', payload: {revision: TS}})),
    };
    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Start re-extract'}));
    await waitFor(() => expect(screen.getByTestId('controller-state')).toHaveTextContent('PROFILE_REEXTRACT_REVIEW_MISMATCH'));
  });

  it('ignores a late durable review after the selected profile scope changes', async () => {
    const pendingReview = deferred<ProfileReextractReview>();
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractReview: vi.fn().mockReturnValue(pendingReview.promise),
      streamProfileReextract: vi.fn(async (_profileId, handlers) => handlers.onEvent({event_id: '11111111-1111-4111-8111-111111111111', operation_id: '22222222-2222-4222-8222-222222222222', profile_id: PROFILE_ID, timestamp: TS, event: 'reextract_review_ready', payload: {revision: TS}})),
    };
    const view = render(<StateHarness api={api} profileId={PROFILE_ID} />);
    await userEvent.click(screen.getByRole('button', {name: 'Start re-extract'}));
    view.rerender(<StateHarness api={api} profileId={OTHER_PROFILE_ID} />);
    await act(async () => { pendingReview.resolve(reviewFixture()); await Promise.resolve(); });
    expect(screen.getByTestId('controller-state')).not.toHaveTextContent('Senior Engineer');
  });
});

describe('useCvManagerState delete guards', () => {
  it('rejects delete when delete_cv is not projected', async () => {
    const deleteCv = vi.fn();
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockResolvedValue({items: [activeItem()]}),
      deleteCv,
    };

    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await userEvent.click(
      screen.getByRole('button', {name: 'Confirm delete'}),
    );

    expect(deleteCv).not.toHaveBeenCalled();
  });

  it('suppresses a duplicate while the first delete remains pending', async () => {
    const deletion = deferred<void>();
    const deleteCv = vi.fn().mockReturnValue(deletion.promise);
    const api: CvManagerApi = {
      fetchCvManager: vi.fn().mockResolvedValue({
        items: [unownedFailedItem()],
      }),
      deleteCv,
    };

    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await waitFor(() =>
      expect(screen.getByTestId('controller-state')).toHaveTextContent(
        'failed-upload.pdf',
      ),
    );

    const confirm = screen.getByRole('button', {name: 'Confirm delete'});
    await userEvent.click(confirm);
    await userEvent.click(confirm);

    expect(deleteCv).toHaveBeenCalledTimes(1);
    deletion.resolve();
  });

  it('aborts stale delete and does not refresh or publish after scope change', async () => {
    const deletion = deferred<void>();
    const deleteCv = vi.fn().mockReturnValue(deletion.promise);
    const fetchCvManager = vi.fn().mockResolvedValue({
      items: [unownedFailedItem()],
    });
    const api: CvManagerApi = {fetchCvManager, deleteCv};
    const view = render(
      <StateHarness api={api} profileId={PROFILE_ID} />,
    );

    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await waitFor(() =>
      expect(screen.getByTestId('controller-state')).toHaveTextContent(
        'failed-upload.pdf',
      ),
    );
    await userEvent.click(
      screen.getByRole('button', {name: 'Confirm delete'}),
    );
    expect(deleteCv).toHaveBeenCalledTimes(1);

    view.rerender(
      <StateHarness api={api} profileId={OTHER_PROFILE_ID} />,
    );

    await act(async () => {
      deletion.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      const state = screen.getByTestId('controller-state');
      expect(state).toHaveTextContent('"items":[]');
      expect(state).toHaveTextContent('"pendingByAttachment":{}');
      expect(state).toHaveTextContent('"errorsByAttachment":{}');
      expect(state).not.toHaveTextContent('failed-upload.pdf');
      expect(fetchCvManager).toHaveBeenCalledTimes(1);
    });
  });

  it('forces a fresh list after a successful delete', async () => {
    const api: CvManagerApi = {
      fetchCvManager: vi
        .fn()
        .mockResolvedValueOnce({items: [unownedFailedItem()]})
        .mockResolvedValueOnce({items: []}),
      deleteCv: vi.fn().mockResolvedValue(undefined),
    };

    render(<StateHarness api={api} />);
    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await waitFor(() =>
      expect(screen.getByTestId('controller-state')).toHaveTextContent(
        'failed-upload.pdf',
      ),
    );

    await userEvent.click(
      screen.getByRole('button', {name: 'Confirm delete'}),
    );

    await waitFor(() => {
      expect(api.deleteCv).toHaveBeenCalledTimes(1);
      expect(api.fetchCvManager).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('controller-state')).toHaveTextContent(
        '"items":[]',
      );
    });
  });
});

describe('CvManagerDrawer server-action and delete behavior', () => {
  it('renders only actions projected by allowed_actions', () => {
    const item = activeItem();
    const controller = {
      ...drawerController(),
      state: {
        phase: 'ready' as const,
        items: [item],
        selectedId: item.id,
        pendingByAttachment: {},
        errorsByAttachment: {},
        deleteTargetId: null,
      },
    };

    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer
          isOpen
          onOpenChange={vi.fn()}
          controller={controller}
          onActivateProfile={vi.fn()}
          onRetryUpload={vi.fn()}
        />
      </Theme>,
    );

    expect(
      screen.getByRole('button', {name: 'Preview'}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: 'Download'}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: 'Re-extract'}),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: 'Delete CV'}),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: /Make active|Activate/i}),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: /Retry/i}),
    ).not.toBeInTheDocument();
  });

  it('does not render Delete for staged or failed rows without delete_cv', () => {
    const staged = {
      ...unownedFailedItem(),
      id: '22222222-3333-4444-8555-666666666666',
      original_name: 'staged.pdf',
      state: 'staged' as const,
      allowed_actions: ['retry_upload' as const],
    };
    const failed = {
      ...unownedFailedItem(),
      original_name: 'failed-without-delete.pdf',
      allowed_actions: ['retry_upload' as const],
    };
    const controller = {
      ...drawerController(),
      state: {
        phase: 'ready' as const,
        items: [staged, failed],
        selectedId: staged.id,
        pendingByAttachment: {},
        errorsByAttachment: {},
        deleteTargetId: null,
      },
    };

    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer isOpen onOpenChange={vi.fn()} controller={controller} />
      </Theme>,
    );

    expect(screen.queryByRole('button', {name: /Delete CV/i})).not.toBeInTheDocument();
  });

  it('renders and calls activate_profile and retry_upload handlers only when projected', async () => {
    const item = {
      ...unownedFailedItem(),
      allowed_actions: ['activate_profile', 'retry_upload'] as const,
    };
    const onActivateProfile = vi.fn();
    const onRetryUpload = vi.fn();
    const controller = {
      ...drawerController(),
      state: {
        phase: 'ready' as const,
        items: [item],
        selectedId: item.id,
        pendingByAttachment: {},
        errorsByAttachment: {},
        deleteTargetId: null,
      },
    };

    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer
          isOpen
          onOpenChange={vi.fn()}
          controller={controller}
          onActivateProfile={onActivateProfile}
          onRetryUpload={onRetryUpload}
        />
      </Theme>,
    );

    await userEvent.click(screen.getByRole('button', {name: 'Activate profile'}));
    await userEvent.click(screen.getByRole('button', {name: 'Retry upload'}));
    expect(onActivateProfile).toHaveBeenCalledWith(item.id);
    expect(onRetryUpload).toHaveBeenCalledWith(item.id);
  });

  it('uses a standard desktop side panel and a narrow fullscreen dialog with focus behavior', async () => {
    const controller = drawerController();
    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer isOpen onOpenChange={vi.fn()} controller={controller} />
      </Theme>,
    );
    const desktopDialog = screen.getByRole('dialog', {name: 'CV Manager'});
    expect(desktopDialog).toHaveAttribute('data-variant', 'standard');
    expect(desktopDialog).toHaveAttribute('data-position', 'right');
    expect(desktopDialog).toHaveAccessibleName('CV Manager');

    cleanup();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: (query: string) => ({
        matches: query === '(max-width: 48rem)',
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    const onOpenChange = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer isOpen onOpenChange={onOpenChange} controller={controller} />
      </Theme>,
    );
    const narrowDialog = screen.getByRole('dialog', {name: 'CV Manager'});
    expect(narrowDialog).toHaveAttribute('data-variant', 'fullscreen');
    expect(narrowDialog).toHaveAccessibleName('CV Manager');
    fireEvent.keyDown(narrowDialog, {key: 'Escape'});
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('opens filename-scoped confirmation through the controller', async () => {
    const item = unownedFailedItem();
    const openDeleteDialog = vi.fn();
    const controller = {
      ...drawerController({openDeleteDialog}),
      state: {
        phase: 'ready' as const,
        items: [item],
        selectedId: item.id,
        pendingByAttachment: {},
        errorsByAttachment: {},
        deleteTargetId: null,
      },
    };

    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer
          isOpen
          onOpenChange={vi.fn()}
          controller={controller}
        />
      </Theme>,
    );

    await userEvent.click(
      screen.getByRole('button', {name: 'Delete CV'}),
    );
    expect(openDeleteDialog).toHaveBeenCalledWith(item.id);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('names the failed file and confirms through confirmDelete', async () => {
    const item = unownedFailedItem();
    const confirmDelete = vi.fn().mockResolvedValue(true);
    const controller = {
      ...drawerController({confirmDelete}),
      state: {
        phase: 'ready' as const,
        items: [item],
        selectedId: item.id,
        pendingByAttachment: {},
        errorsByAttachment: {},
        deleteTargetId: item.id,
      },
    };

    render(
      <Theme theme={neutralTheme}>
        <CvManagerDrawer
          isOpen
          onOpenChange={vi.fn()}
          controller={controller}
        />
      </Theme>,
    );

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('failed-upload.pdf');
    await userEvent.click(
      within(dialog).getByRole('button', {name: 'Delete CV'}),
    );
    expect(confirmDelete).toHaveBeenCalledWith(item.id);
  });
});

describe('ProfileDeleteDialog ownership', () => {
  it('uses the exact destructive profile action label', () => {
    const profile: ProfileListItem = {
      id: PROFILE_ID,
      display_name: 'Profile A',
      cv_filename: 'resume.pdf',
      attachment_state: 'active',
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: 'v1',
      source_hash: 'source-a',
      state: 'ready',
      setup_status: null,
      is_active: true,
      created_at: TS,
      updated_at: TS,
      last_opened_at: TS,
    };
    render(
      <Theme theme={neutralTheme}>
        <ProfileDeleteDialog
          profile={profile}
          isOpen
          isActionLoading={false}
          onOpenChange={vi.fn()}
          onConfirm={vi.fn().mockResolvedValue(undefined)}
        />
      </Theme>,
    );

    expect(
      screen.getByRole('button', {
        name: 'Delete profile and all data',
      }),
    ).toBeInTheDocument();
  });

  it('keeps Saved Jobs on the relocated generic request hook', () => {
    expect(savedJobsStateSource).toContain("../lib/hooks/useLatestRequest");
    expect(savedJobsStateSource).not.toContain("../observability/useLatestRequest");
  });
});

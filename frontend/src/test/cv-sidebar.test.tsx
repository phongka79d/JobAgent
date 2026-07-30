/**
 * CV sidebar + shared upload path tests (04A).
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useState} from 'react';

import {App} from '../app/App';
import {
  ChatApiError,
  getActiveCvUrl,
  SIDEBAR_CV_TURN_MESSAGE,
} from '../features/profile/api';
import type {CvTailoringController} from '../features/cv-tailoring/state';
import type {ProfileReextractStreamHandlers} from '../features/cv-manager/api';
import {createEmptySavedJobsController} from '../features/jobs/savedJobsState';
import {
  CvSidebar,
  type CvSidebarProps,
} from '../features/profile/CvSidebar';
import {
  initialProfileWorkspaceState,
  type ProfileWorkspaceController,
} from '../features/profile/workspaceState';
import {
  parseAttachmentPublic,
  parseCvUploadResponse,
  parseProfileReadResponse,
  type CvUploadResponse,
  type ProfileReadResponse,
} from '../features/profile/types';
import {getApiBaseUrl} from '../lib/api/chat';

const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const PROFILE_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const PROFILE_B_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const CONVERSATION_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const NOW = '2026-07-23T10:00:00Z';

function emptyTailoringController(): CvTailoringController {
  return {
    state: {
      profileScopeKey: 'none',
      sessions: {phase: 'idle', data: null, error: null},
      selectedSessionId: null,
      selectedVersionId: null,
      detail: {phase: 'idle', data: null, error: null},
      draft: null,
      draftDirty: false,
      conflict: false,
      stream: {phase: 'idle', data: null, error: null},
      lastOutcome: null,
      lastOutcomeSource: null,
      pendingFocus: null,
      retryRequest: null,
    },
    loadSessions: vi.fn().mockResolvedValue(undefined),
    openSession: vi.fn().mockResolvedValue(true),
    createSession: vi.fn().mockResolvedValue(null),
    createAiVersion: vi.fn().mockResolvedValue(false),
    setDraft: vi.fn(),
    undoIssue: vi.fn(),
    focusIssue: vi.fn(),
    retryIssue: vi.fn(),
    saveManualVersion: vi.fn().mockResolvedValue(false),
    selectVersion: vi.fn().mockResolvedValue(false),
    deleteSession: vi.fn().mockResolvedValue(true),
  };
}

function productControllers(): Pick<
  CvSidebarProps,
  'workspace' | 'savedJobs' | 'tailoring' | 'savedJobsInvalidateKey'
> {
  const workspace: ProfileWorkspaceController = {
    state: {
      ...initialProfileWorkspaceState,
      phase: 'ready',
      pending: new Set(),
    },
    activate: vi.fn().mockResolvedValue(undefined),
    createConversation: vi.fn().mockResolvedValue(undefined),
    selectConversation: vi.fn().mockResolvedValue(undefined),
    deleteConversation: vi.fn().mockResolvedValue(false),
    renameProfile: vi.fn().mockResolvedValue(false),
    deleteProfile: vi.fn().mockResolvedValue(false),
    reload: vi.fn().mockResolvedValue(undefined),
    adoptBootstrap: vi.fn(),
  };
  return {
    workspace,
    savedJobs: createEmptySavedJobsController(),
    tailoring: emptyTailoringController(),
    savedJobsInvalidateKey: 0,
  };
}

function emptyProfile(): ProfileReadResponse {
  return {
    present: false,
    profile: null,
    preferences: null,
    active_attachment: null,
    draft_present: false,
    pending_attachment: null,
  };
}

function activeProfile(
  name = 'resume.pdf',
): ProfileReadResponse {
  return {
    present: true,
    profile: {
      summary: 'Engineer',
      current_title: 'Software Engineer',
    },
    preferences: {
      target_roles: [],
      preferred_locations: [],
      acceptable_work_modes: [],
      target_seniority: [],
    },
    active_attachment: {
      id: ATTACHMENT_ID,
      original_name: name,
      mime_type: 'application/pdf',
      size_bytes: 1024,
      page_count: 2,
      state: 'active',
      failure_code: null,
    },
    draft_present: false,
    pending_attachment: null,
  };
}

function uploadResponse(
  name = 'new-cv.pdf',
  id = ATTACHMENT_ID,
  startExtraction = true,
): CvUploadResponse {
  return {
    attachment: {
      id,
      original_name: name,
      mime_type: 'application/pdf',
      size_bytes: 2048,
      page_count: 1,
      state: 'staged',
      failure_code: null,
    },
    outcome: 'new_pending',
    profile: null,
    draft: null,
    bootstrap: {
      profile: {
        id: PROFILE_ID,
        display_name: name,
        cv_filename: name,
        attachment_state: 'staged',
        location: null,
        skill_tags: [],
        skill_count: 0,
        extraction_version: null,
        source_hash: null,
        state: 'pending',
        setup_status: 'awaiting_extraction',
        is_active: true,
        created_at: NOW,
        updated_at: NOW,
        last_opened_at: NOW,
      },
      conversation: {
        id: CONVERSATION_ID,
        profile_id: PROFILE_ID,
        title: 'New chat',
        created_at: NOW,
        updated_at: NOW,
        last_opened_at: NOW,
        is_selected: true,
      },
      start_extraction: startExtraction,
    },
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  // AppShell responsive hooks
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

describe('profile transport parsers', () => {
  it('parses empty and active profile without storage_path', () => {
    expect(parseProfileReadResponse({present: false})).toEqual(emptyProfile());
    const active = parseProfileReadResponse({
      present: true,
      profile: {summary: 'Hi', current_title: 'Dev'},
      preferences: {
        target_roles: ['eng'],
        preferred_locations: [],
        acceptable_work_modes: [],
        target_seniority: [],
      },
      active_attachment: {
        id: ATTACHMENT_ID,
        original_name: 'cv.pdf',
        mime_type: 'application/pdf',
        size_bytes: 10,
        page_count: 1,
        state: 'active',
        failure_code: null,
      },
    });
    expect(active.present).toBe(true);
    expect(active.active_attachment?.original_name).toBe('cv.pdf');
  });

  it('rejects storage_path leakage in attachment and upload payloads', () => {
    expect(() =>
      parseAttachmentPublic({
        id: ATTACHMENT_ID,
        original_name: 'x.pdf',
        mime_type: 'application/pdf',
        size_bytes: 1,
        page_count: 1,
        state: 'staged',
        failure_code: null,
        storage_path: 'secret/path',
      }),
    ).toThrow(/storage_path/);
    expect(() =>
      parseCvUploadResponse({
        attachment: {
          id: ATTACHMENT_ID,
          original_name: 'x.pdf',
          mime_type: 'application/pdf',
          size_bytes: 1,
          page_count: 1,
          state: 'staged',
          failure_code: null,
        },
        outcome: 'new_pending',
        profile: null,
        draft: null,
        bootstrap: null,
        storage_path: 'nope',
      }),
    ).toThrow(/storage_path/);
  });

  it('builds active CV URL from VITE_API_BASE_URL only', () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    try {
      // @ts-expect-error test mutation of import.meta.env
      import.meta.env.VITE_API_BASE_URL = 'http://localhost:8000/';
      expect(getApiBaseUrl()).toBe('http://localhost:8000');
      expect(getActiveCvUrl()).toBe('http://localhost:8000/api/profile/cv');
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

describe('CvSidebar empty / active states', () => {
  it('recovers product navigation from a legacy zero-width SideNav resize value', async () => {
    const legacyResizeKey =
      'astryx-resizable:jobagent-observability-sidebar-width-v2';
    window.localStorage.setItem(legacyResizeKey, JSON.stringify(0));
    try {
      render(
        <Theme theme={neutralTheme}>
          <CvSidebar
            {...productControllers()}
            isUploadDisabled={false}
            onSidebarUploadSuccess={vi.fn()}
            deps={{loadProfile: vi.fn().mockResolvedValue(emptyProfile()), uploadCv: vi.fn()}}
          />
        </Theme>,
      );

      expect(screen.getByTestId('jobagent-cv-sidebar')).not.toHaveStyle({width: '0px'});
      await userEvent.click(screen.getByRole('button', {name: 'Saved Jobs'}));
      expect(screen.getByTestId('jobagent-product-sidebar')).toHaveAttribute(
        'data-selected-destination',
        'saved-jobs',
      );
    } finally {
      window.localStorage.removeItem(legacyResizeKey);
    }
  });

  it('reloads active profile details when the workspace profile changes', async () => {
    const profileA = {
      ...uploadResponse('profile-a.pdf').bootstrap!.profile,
      attachment_state: 'active' as const,
      extraction_version: 'v1',
      source_hash: 'profile-a',
      state: 'ready' as const,
      setup_status: null,
    };
    const profileB = {
      ...profileA,
      id: PROFILE_B_ID,
      display_name: 'Profile B',
      cv_filename: 'profile-b.pdf',
      source_hash: 'profile-b',
      is_active: false,
    };
    const profileBDetail = activeProfile('profile-b.pdf');
    profileBDetail.active_attachment = {
      ...profileBDetail.active_attachment!,
      id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
    };
    const loadProfile = vi
      .fn()
      .mockResolvedValueOnce(activeProfile('profile-a.pdf'))
      .mockResolvedValueOnce(profileBDetail);

    function Harness() {
      const [activeProfileId, setActiveProfileId] = useState(PROFILE_ID);
      const workspace: ProfileWorkspaceController = {
        state: {
          profiles: [
            {...profileA, is_active: activeProfileId === PROFILE_ID},
            {...profileB, is_active: activeProfileId === PROFILE_B_ID},
          ],
          activeProfileId,
          selectedConversationId: CONVERSATION_ID,
          conversations: [],
          pending: new Set(),
          error: null,
        },
        activate: vi.fn(),
        createConversation: vi.fn(),
        selectConversation: vi.fn(),
        deleteConversation: vi.fn(),
        renameProfile: vi.fn(),
        deleteProfile: vi.fn(),
        reload: vi.fn(),
        adoptBootstrap: vi.fn(),
      };
      return (
        <>
          <button type="button" onClick={() => setActiveProfileId(PROFILE_B_ID)}>
            Switch profile
          </button>
          <CvSidebar
            {...productControllers()}
            isUploadDisabled={false}
            onSidebarUploadSuccess={vi.fn()}
            workspace={workspace}
            deps={{loadProfile, uploadCv: vi.fn()}}
          />
        </>
      );
    }

    render(
      <Theme theme={neutralTheme}>
        <Harness />
      </Theme>,
    );
    expect(await screen.findByTestId('jobagent-active-cv-filename')).toHaveTextContent(
      'profile-a.pdf',
    );

    await userEvent.click(screen.getByRole('button', {name: 'Switch profile'}));

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-active-cv-filename')).toHaveTextContent(
        'profile-b.pdf',
      );
    });
    expect(loadProfile).toHaveBeenCalledTimes(2);
  });

  it('withholds a global profile result until the rehydrated workspace scope is ready', async () => {
    const profileA = {
      ...uploadResponse('ava.pdf').bootstrap!.profile,
      attachment_state: 'active' as const,
      extraction_version: 'v1',
      source_hash: 'ava-source',
      state: 'ready' as const,
      setup_status: null,
    };
    const profileB = {
      ...profileA,
      id: PROFILE_B_ID,
      display_name: 'Noah',
      cv_filename: 'noah.pdf',
      source_hash: 'noah-source',
      is_active: false,
    };
    const avaProfile = activeProfile('ava.pdf');
    avaProfile.profile!.current_title = 'Ava Engineer';
    const noahProfile = activeProfile('noah.pdf');
    noahProfile.profile!.current_title = 'Noah Principal';
    let resolveStaleGlobalProfile!: (profile: ProfileReadResponse) => void;
    let resolveReadyProfile!: (profile: ProfileReadResponse) => void;
    const staleGlobalProfile = new Promise<ProfileReadResponse>((resolve) => {
      resolveStaleGlobalProfile = resolve;
    });
    const readyProfile = new Promise<ProfileReadResponse>((resolve) => {
      resolveReadyProfile = resolve;
    });
    const loadProfile = vi
      .fn()
      .mockResolvedValueOnce(avaProfile)
      .mockReturnValueOnce(staleGlobalProfile)
      .mockReturnValueOnce(readyProfile);

    function Harness() {
      const [phase, setPhase] = useState<'ready' | 'rehydrating'>('ready');
      const [activeProfileId, setActiveProfileId] = useState(PROFILE_ID);
      const [refreshKey, setRefreshKey] = useState(0);
      const workspace: ProfileWorkspaceController = {
        state: {
          phase,
          profiles: [
            {...profileA, is_active: activeProfileId === PROFILE_ID},
            {...profileB, is_active: activeProfileId === PROFILE_B_ID},
          ],
          activeProfileId,
          selectedConversationId: CONVERSATION_ID,
          conversations: [],
          pending: new Set(),
          error: null,
        },
        activate: vi.fn(),
        createConversation: vi.fn(),
        selectConversation: vi.fn(),
        deleteConversation: vi.fn(),
        renameProfile: vi.fn(),
        deleteProfile: vi.fn(),
        reload: vi.fn(),
        adoptBootstrap: vi.fn(),
      };
      return (
        <>
          <button type="button" onClick={() => setRefreshKey(1)}>
            Refresh global profile
          </button>
          <button type="button" onClick={() => setPhase('rehydrating')}>
            Start rehydration
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveProfileId(PROFILE_B_ID);
              setPhase('ready');
            }}
          >
            Publish Noah workspace
          </button>
          <CvSidebar
            {...productControllers()}
            isUploadDisabled={false}
            onSidebarUploadSuccess={vi.fn()}
            workspace={workspace}
            refreshKey={refreshKey}
            deps={{loadProfile, uploadCv: vi.fn()}}
          />
        </>
      );
    }

    render(
      <Theme theme={neutralTheme}>
        <Harness />
      </Theme>,
    );
    expect(await screen.findByTestId('jobagent-active-cv-filename')).toHaveTextContent(
      'ava.pdf',
    );

    await userEvent.click(screen.getByRole('button', {name: 'Refresh global profile'}));
    await waitFor(() => expect(loadProfile).toHaveBeenCalledTimes(2));
    await userEvent.click(screen.getByRole('button', {name: 'Start rehydration'}));
    await act(async () => {
      resolveStaleGlobalProfile(noahProfile);
      await Promise.resolve();
    });

    expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent('Loading...');
    expect(screen.queryByText('Noah Principal')).not.toBeInTheDocument();
    expect(screen.getByTestId('jobagent-active-cv-filename')).not.toHaveTextContent(
      'noah.pdf',
    );

    await userEvent.click(screen.getByRole('button', {name: 'Publish Noah workspace'}));
    await waitFor(() => expect(loadProfile).toHaveBeenCalledTimes(3));
    await act(async () => {
      resolveReadyProfile(noahProfile);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
        'Active - Noah Principal',
      );
      expect(screen.getByTestId('jobagent-active-cv-filename')).toHaveTextContent(
        'noah.pdf',
      );
    });
  });

  it('shows empty profile state, upload, and disabled download', async () => {
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    const onSuccess = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={onSuccess}
          deps={{loadProfile, uploadCv: vi.fn()}}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
        'No approved profile',
      );
    });
    expect(screen.getByTestId('jobagent-active-cv-filename')).toHaveTextContent(
      'No active CV',
    );
    expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    expect(screen.getByText('Upload CV')).toBeInTheDocument();
    const download = screen.getByTestId('jobagent-cv-download');
    expect(download).toBeDisabled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('shows active filename, profile state, and enables view/download', async () => {
    const loadProfile = vi.fn().mockResolvedValue(activeProfile('my-cv.pdf'));
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          deps={{
            loadProfile,
            uploadCv: vi.fn(),
            getActiveCvUrl: () => 'http://api.test/api/profile/cv',
          }}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-active-cv-filename'),
      ).toHaveTextContent('my-cv.pdf');
    });
    expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
      /Active/,
    );
    expect(screen.getByText('Upload new CV')).toBeInTheDocument();

    const download = screen.getByTestId('jobagent-cv-download');
    expect(download).not.toBeDisabled();
    await userEvent.click(download);
    expect(openSpy).toHaveBeenCalledWith(
      'http://api.test/api/profile/cv',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('disables upload while interaction is locked', async () => {
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled
          onSidebarUploadSuccess={vi.fn()}
          deps={{loadProfile, uploadCv: vi.fn()}}
        />
      </Theme>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    });
    const input = screen.getByTestId('jobagent-cv-upload') as HTMLInputElement;
    // FileInput disables the hidden input and/or marks the trigger aria-disabled.
    const trigger = input.closest('[role="button"]');
    expect(
      input.disabled ||
        input.getAttribute('aria-disabled') === 'true' ||
        trigger?.getAttribute('aria-disabled') === 'true' ||
        trigger?.getAttribute('data-disabled') === 'true',
    ).toBe(true);
  });

  it('surfaces stable upload errors without success callback', async () => {
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    const upload = vi
      .fn()
      .mockRejectedValue(
        new ChatApiError(422, 'PDF_TOO_LARGE', 'PDF exceeds maximum size'),
      );
    const onSuccess = vi.fn();

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={onSuccess}
          deps={{loadProfile, uploadCv: upload}}
        />
      </Theme>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    });

    const file = new File(['%PDF-1.4 fake'], 'big.pdf', {
      type: 'application/pdf',
    });
    const input = screen.getByTestId('jobagent-cv-upload') as HTMLInputElement;
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(upload).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByText(/PDF exceeds maximum size/)).toBeInTheDocument();
      expect(screen.getByText(/PDF_TOO_LARGE/)).toBeInTheDocument();
    });
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('rejects retry responses that replace the bootstrap conversation', async () => {
    const pending = uploadResponse('retry.pdf').bootstrap!;
    const workspace: ProfileWorkspaceController = {
      state: {
        profiles: [{
          ...pending.profile,
          attachment_state: 'failed',
          setup_status: 'extraction_failed',
        }],
        activeProfileId: PROFILE_ID,
        selectedConversationId: CONVERSATION_ID,
        conversations: [pending.conversation],
        pending: new Set(),
        error: null,
      },
      activate: vi.fn(),
      createConversation: vi.fn(),
      selectConversation: vi.fn(),
      deleteConversation: vi.fn(),
      renameProfile: vi.fn(),
      deleteProfile: vi.fn(),
      reload: vi.fn(),
      adoptBootstrap: vi.fn(),
    };
    const retryResponse: CvUploadResponse = {
      ...uploadResponse('retry.pdf'),
      outcome: 'retry_pending',
      bootstrap: {
        ...pending,
        conversation: {
          ...pending.conversation,
          id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        },
      },
    };
    const upload = vi.fn().mockResolvedValue(retryResponse);
    const onSuccess = vi.fn();

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={onSuccess}
          workspace={workspace}
          deps={{loadProfile: vi.fn().mockResolvedValue(emptyProfile()), uploadCv: upload}}
        />
      </Theme>,
    );

    await userEvent.click(await screen.findByRole('button', {name: 'Retry'}));
    const input = screen.getByLabelText('Retry profile CV');
    fireEvent.change(input, {
      target: {
        files: [new File(['%PDF-1.4'], 'retry.pdf', {type: 'application/pdf'})],
      },
    });

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(screen.getByText(/inconsistent profile ownership/i)).toBeInTheDocument();
    });
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('re-extracts the selected ready profile through its profile id', async () => {
    const base = uploadResponse('selected.pdf').bootstrap!;
    const ready = {
      ...base.profile,
      attachment_state: 'active' as const,
      extraction_version: 'v1',
      source_hash: 'source-selected',
      state: 'ready' as const,
      setup_status: null,
    };
    const workspace: ProfileWorkspaceController = {
      state: {
        profiles: [ready],
        activeProfileId: PROFILE_ID,
        selectedConversationId: CONVERSATION_ID,
        conversations: [base.conversation],
        pending: new Set(),
        error: null,
      },
      activate: vi.fn(),
      createConversation: vi.fn(),
      selectConversation: vi.fn(),
      deleteConversation: vi.fn(),
      renameProfile: vi.fn(),
      deleteProfile: vi.fn(),
      reload: vi.fn(),
      adoptBootstrap: vi.fn(),
    };
    const reextract = vi.fn(async (profileId: string, handlers: ProfileReextractStreamHandlers) => {
      handlers.onEvent({
        event_id: '11111111-1111-4111-8111-111111111111',
        operation_id: '22222222-2222-4222-8222-222222222222',
        profile_id: profileId,
        timestamp: '2026-07-28T10:00:00Z',
        event: 'reextract_failed',
        payload: {code: 'TEST_FAILURE', summary: 'Test failure', draft_available: false},
      });
    });

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          workspace={workspace}
          deps={{
            loadProfile: vi.fn().mockResolvedValue(activeProfile('selected.pdf')),
            uploadCv: vi.fn(),
            cvManager: {streamProfileReextract: reextract},
          }}
        />
      </Theme>,
    );

    await userEvent.click(
      await screen.findByRole('button', {name: 'Actions for selected.pdf'}),
    );
    await userEvent.click(await screen.findByText('Re-extract CV'));

    expect(reextract).toHaveBeenCalledTimes(1);
    expect(reextract).toHaveBeenCalledWith(
      PROFILE_ID,
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });
});

describe('shared sidebar upload → chat turn', () => {
  it('adopts the server conversation before starting one ID-only turn', async () => {
    const loadHistory = vi.fn().mockResolvedValue({items: [], next_cursor: null});
    const loadConversationHistory = vi.fn().mockResolvedValue({items: [], next_cursor: null});
    const loadProfile = vi
      .fn()
      .mockResolvedValueOnce(emptyProfile())
      .mockResolvedValue(emptyProfile());
    const upload = vi.fn().mockResolvedValue(uploadResponse('side.pdf'));
    const sendConversationTurn = vi.fn().mockResolvedValue(undefined);

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {loadHistory, loadConversationHistory, sendConversationTurn, uploadCv: upload},
            sidebar: {loadProfile, uploadCv: upload},
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({items: [], active_profile_id: null}),
            },
          }}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-cv-sidebar')).toBeInTheDocument();
      expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument();
    });

    const sidebarInput = screen.getByTestId(
      'jobagent-cv-upload',
    ) as HTMLInputElement;
    const file = new File(['%PDF-1.4'], 'side.pdf', {type: 'application/pdf'});
    await userEvent.upload(sidebarInput, file);

    await waitFor(() => {
      expect(upload).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(sendConversationTurn).toHaveBeenCalledTimes(1);
    });

    expect(sendConversationTurn.mock.calls[0]![0]).toBe(CONVERSATION_ID);
    const body = sendConversationTurn.mock.calls[0]![1] as {
      message: string;
      attachment_ids?: string[];
    };
    expect(body.message).toBe(SIDEBAR_CV_TURN_MESSAGE);
    expect(body.attachment_ids).toEqual([ATTACHMENT_ID]);
    // No File/Blob/PDF body on the turn request.
    expect(JSON.stringify(body)).not.toMatch(/storage_path|%PDF/);
  });

  it('routes composer upload through bootstrap adoption before extraction', async () => {
    const upload = vi.fn().mockResolvedValue(uploadResponse('composer.pdf'));
    const sendConversationTurn = vi.fn().mockResolvedValue(undefined);
    const readyProfileId = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
    const readyConversationId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
    const readyProfile = {
      id: readyProfileId,
      display_name: 'ready.pdf',
      cv_filename: 'ready.pdf',
      attachment_state: 'active' as const,
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: 'fixture-v1',
      source_hash: 'fixture-source',
      state: 'ready' as const,
      setup_status: null,
      is_active: true,
      created_at: NOW,
      updated_at: NOW,
      last_opened_at: NOW,
    };
    const readyConversation = {
      id: readyConversationId,
      profile_id: readyProfileId,
      title: 'Existing chat',
      created_at: NOW,
      updated_at: NOW,
      last_opened_at: NOW,
      is_selected: true,
    };

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {
              loadHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
              loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
              sendConversationTurn,
              uploadCv: upload,
            },
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue(emptyProfile()),
              uploadCv: upload,
            },
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [readyProfile],
                active_profile_id: readyProfileId,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [readyConversation],
                next_cursor: null,
              }),
            },
          }}
        />
      </Theme>,
    );

    const getComposerInput = () => {
      const composerUpload = screen.getByTestId('jobagent-chat-pdf-upload');
      return composerUpload instanceof HTMLInputElement
        ? composerUpload
        : composerUpload.querySelector('input[type="file"]');
    };
    await waitFor(() => expect(getComposerInput()).not.toBeDisabled());
    const composerUpload = screen.getByTestId('jobagent-chat-pdf-upload');
    const composerInput =
      composerUpload instanceof HTMLInputElement
        ? composerUpload
        : composerUpload.querySelector('input[type="file"]');
    expect(composerInput).not.toBeNull();
    await userEvent.upload(
      composerInput as HTMLInputElement,
      new File(['%PDF-1.4'], 'composer.pdf', {type: 'application/pdf'}),
    );

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(sendConversationTurn).toHaveBeenCalledTimes(1));
    expect(sendConversationTurn.mock.calls[0]![0]).toBe(CONVERSATION_ID);
    expect(sendConversationTurn.mock.calls[0]![1]).toMatchObject({
      attachment_ids: [ATTACHMENT_ID],
    });
  });

  it('does not restart extraction when an existing pending bootstrap says false', async () => {
    const upload = vi.fn().mockResolvedValue({
      ...uploadResponse('pending.pdf', ATTACHMENT_ID, false),
      outcome: 'existing_pending',
    });
    const sendConversationTurn = vi.fn();

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {
              loadHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
              loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
              sendConversationTurn,
            },
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue(emptyProfile()),
              uploadCv: upload,
            },
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({items: [], active_profile_id: null}),
            },
          }}
        />
      </Theme>,
    );

    const file = new File(['%PDF-1.4'], 'pending.pdf', {type: 'application/pdf'});
    await userEvent.upload(screen.getByTestId('jobagent-cv-upload'), file);
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    expect(sendConversationTurn).not.toHaveBeenCalled();
  });

  it('renders profile and conversation navigation in the mobile drawer', async () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: (query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function close() {
      this.removeAttribute('open');
    };
    const base = uploadResponse('mobile.pdf').bootstrap!;
    const readyProfile = {
      ...base.profile,
      attachment_state: 'active' as const,
      extraction_version: 'v1',
      source_hash: 'source-mobile',
      state: 'ready' as const,
      setup_status: null,
    };

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {
              loadHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
              loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
            },
            sidebar: {loadProfile: vi.fn().mockResolvedValue(activeProfile('mobile.pdf'))},
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [readyProfile],
                active_profile_id: PROFILE_ID,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [base.conversation],
                next_cursor: null,
              }),
            },
          }}
        />
      </Theme>,
    );

    await userEvent.click(await screen.findByRole('button', {name: 'Open navigation'}));

    const drawer = screen.getByRole('dialog', {name: 'Navigation'});
    expect(drawer).toBeInTheDocument();
    expect(await screen.findByTestId('jobagent-profile-conversation-sidebar')).toBeInTheDocument();
    expect(within(drawer).getAllByText('mobile.pdf').length).toBeGreaterThan(0);
    expect(
      within(drawer).getAllByText(base.conversation.title).length,
    ).toBeGreaterThan(0);
  });
});

describe('product CV Manager overview entry point', () => {
  it('does not render Retry upload in the production sidebar without a retry handler', async () => {
    const base = uploadResponse('failed-resume.pdf').bootstrap!;
    const failedProfile = {
      ...base.profile,
      attachment_state: 'failed' as const,
      state: 'pending' as const,
      setup_status: 'extraction_failed' as const,
    };
    const workspace: ProfileWorkspaceController = {
      state: {
        profiles: [failedProfile],
        activeProfileId: PROFILE_ID,
        selectedConversationId: CONVERSATION_ID,
        conversations: [base.conversation],
        pending: new Set(),
        error: null,
      },
      activate: vi.fn(),
      createConversation: vi.fn(),
      selectConversation: vi.fn(),
      deleteConversation: vi.fn(),
      renameProfile: vi.fn(),
      deleteProfile: vi.fn(),
      reload: vi.fn(),
      adoptBootstrap: vi.fn(),
    };

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          workspace={workspace}
          deps={{
            loadProfile: vi.fn().mockResolvedValue(emptyProfile()),
            cvManager: {
              fetchCvManager: vi.fn().mockResolvedValue({
                items: [{
                  id: ATTACHMENT_ID,
                  original_name: 'failed-resume.pdf',
                  state: 'failed',
                  failure_code: 'EXTRACTION_FAILED',
                  page_count: null,
                  file_available: false,
                  profile_id: null,
                  profile_display_name: null,
                  profile_state: null,
                  is_active_profile: false,
                  allowed_actions: ['retry_upload'],
                  created_at: NOW,
                  updated_at: NOW,
                }],
              }),
            },
          }}
        />
      </Theme>,
    );

    await userEvent.click(await screen.findByRole('button', {name: 'Manage CVs'}));
    const drawer = await screen.findByRole('dialog', {name: /CV Manager|Manage CVs/i});

    expect(within(drawer).queryByRole('button', {name: 'Retry upload'})).not.toBeInTheDocument();
  });

  it('opens Manage CVs and deletes only the unowned attachment', async () => {
    const base = uploadResponse('managed-resume.pdf').bootstrap!;
    const readyProfile = {
      ...base.profile,
      attachment_state: 'active' as const,
      extraction_version: 'v1',
      source_hash: 'managed-source',
      state: 'ready' as const,
      setup_status: null,
    };
    const deleteProfile = vi.fn().mockResolvedValue(true);
    const workspace: ProfileWorkspaceController = {
      state: {
        profiles: [readyProfile],
        activeProfileId: PROFILE_ID,
        selectedConversationId: CONVERSATION_ID,
        conversations: [base.conversation],
        pending: new Set(),
        error: null,
      },
      activate: vi.fn(),
      createConversation: vi.fn(),
      selectConversation: vi.fn(),
      deleteConversation: vi.fn(),
      renameProfile: vi.fn(),
      deleteProfile,
      reload: vi.fn(),
      adoptBootstrap: vi.fn(),
    };
    const fetchCvManager = vi.fn().mockResolvedValue({
      items: [
        {
          id: ATTACHMENT_ID,
          original_name: 'managed-resume.pdf',
          state: 'failed',
          failure_code: 'EXTRACTION_FAILED',
          page_count: null,
          file_available: false,
          profile_id: null,
          profile_display_name: null,
          profile_state: null,
          is_active_profile: false,
          allowed_actions: ['delete_cv'],
          created_at: NOW,
          updated_at: NOW,
        },
      ],
    });
    const deleteCv = vi.fn().mockResolvedValue(undefined);

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          {...productControllers()}
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          workspace={workspace}
          deps={{
            loadProfile: vi.fn().mockResolvedValue(
              activeProfile('managed-resume.pdf'),
            ),
            uploadCv: vi.fn(),
            cvManager: {
              fetchCvManager,
              deleteCv,
            },
          }}
        />
      </Theme>,
    );

    await userEvent.click(
      await screen.findByRole('button', {name: 'Manage CVs'}),
    );
    const drawer = await screen.findByRole('dialog', {
      name: /CV Manager|Manage CVs/i,
    });
    expect(
      within(drawer).getByText('managed-resume.pdf'),
    ).toBeInTheDocument();

    await userEvent.click(
      within(drawer).getByRole('button', {name: 'Delete CV'}),
    );
    const confirmation = await screen.findByRole('alertdialog');
    expect(confirmation).toHaveTextContent('managed-resume.pdf');
    await userEvent.click(
      within(confirmation).getByRole('button', {name: 'Delete CV'}),
    );

    await waitFor(() => {
      expect(deleteCv).toHaveBeenCalledTimes(1);
      expect(deleteProfile).not.toHaveBeenCalled();
    });
  });
});

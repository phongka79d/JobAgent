import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {
  App,
  freshTailoringRequest,
  reloadLatestTailoring,
  selectedScorableJobId,
} from './App';
import type {
  ConversationSummary,
  ProfileListItem,
  ProfileListResponse,
} from '../features/profile/conversationTypes';
import type {TailoringSessionDetailResponse} from '../features/cv-tailoring/types';
import {ChatApiError} from '../lib/api/chat';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute('open', '');
    };
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function close() {
      this.removeAttribute('open');
    };
  }
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return {promise, resolve, reject};
}

function appProfile(id: string, isActive: boolean): ProfileListItem {
  return {
    id,
    display_name: id,
    cv_filename: `${id}.pdf`,
    attachment_state: 'active',
    location: null,
    skill_tags: [],
    skill_count: 0,
    extraction_version: 'v1',
    source_hash: id,
    state: 'ready',
    setup_status: null,
    is_active: isActive,
    created_at: '2026-07-28T00:00:00Z',
    updated_at: '2026-07-28T00:00:00Z',
    last_opened_at: '2026-07-28T00:00:00Z',
  };
}

function appConversation(id: string, profileId: string): ConversationSummary {
  return {
    id,
    profile_id: profileId,
    title: id,
    created_at: '2026-07-28T00:00:00Z',
    updated_at: '2026-07-28T00:00:00Z',
    last_opened_at: '2026-07-28T00:00:00Z',
    is_selected: true,
  };
}

const CONFLICT_PROFILE_ID = '11111111-1111-4111-8111-111111111111';
const CONFLICT_OPERATION_ID = '22222222-2222-4222-8222-222222222222';
const CONFLICT_REVISION = '2026-07-31T12:00:00.000Z';
const SWITCHED_PROFILE_ID = '44444444-4444-4444-8444-444444444444';

function reextractReview(
  profileId: string,
  operationId: string | null,
  source: 'agent_update' | 'reextract',
) {
  return {
    profile_id: profileId,
    source,
    operation_id: operationId,
    operation_state: source === 'reextract' ? 'review_ready' : null,
    revision: CONFLICT_REVISION,
    current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Current', current_title: null, skill_labels: []},
    proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Proposed', current_title: null, skill_labels: []},
    changed_fields: [],
    preference_changes: [],
    skills_added: [],
    skills_removed: [],
    collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0},
    extraction_confidence: null,
    can_approve: true,
    can_discard: true,
  };
}

function renderUploadConflictApp(
  detail: Record<string, unknown>,
  getProfileReextractOperation: ReturnType<typeof vi.fn>,
  getProfileReextractReview: ReturnType<typeof vi.fn>,
  startReextract: ReturnType<typeof vi.fn>,
) {
  const profile = appProfile(CONFLICT_PROFILE_ID, true);
  const fetchCvManager = vi.fn().mockResolvedValue({items: []});
  render(
    <Theme theme={neutralTheme}>
      <App
        deps={{
          workspace: {
            fetchProfiles: vi.fn().mockResolvedValue({items: [profile], active_profile_id: profile.id}),
            fetchProfileConversations: vi.fn().mockResolvedValue({items: [appConversation('conflict-conversation', profile.id)], next_cursor: null}),
          },
          chat: {loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null})},
          sidebar: {
            loadProfile: vi.fn().mockResolvedValue({
              present: true,
              profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
              preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
              active_attachment: {id: 'attachment-conflict', original_name: 'conflict.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
              draft_present: false,
              pending_attachment: null,
              pending_review: null,
            }),
            uploadCv: vi.fn().mockRejectedValue(new ChatApiError(409, String(detail.code), String(detail.summary), detail)),
          },
          cvManager: {
            fetchCvManager,
            getProfileReextractOperation,
            getProfileReextractReview,
            streamProfileReextract: startReextract,
          },
        }}
      />
    </Theme>,
  );
  return {profile, fetchCvManager};
}

function renderChatConflictApp(
  detail: Record<string, unknown>,
  getProfileReextractOperation: ReturnType<typeof vi.fn>,
  getProfileReextractReview: ReturnType<typeof vi.fn>,
  startReextract: ReturnType<typeof vi.fn>,
) {
  const profile = appProfile(CONFLICT_PROFILE_ID, true);
  const fetchCvManager = vi.fn().mockResolvedValue({items: []});
  render(
    <Theme theme={neutralTheme}>
      <App
        deps={{
          workspace: {
            fetchProfiles: vi.fn().mockResolvedValue({items: [profile], active_profile_id: profile.id}),
            fetchProfileConversations: vi.fn().mockResolvedValue({items: [appConversation('chat-conflict-conversation', profile.id)], next_cursor: null}),
          },
          chat: {
            loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
            uploadCv: vi.fn().mockRejectedValue(new ChatApiError(409, String(detail.code), String(detail.summary), detail)),
          },
          sidebar: {
            loadProfile: vi.fn().mockResolvedValue({
              present: true,
              profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
              preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
              active_attachment: {id: 'attachment-chat-conflict', original_name: 'chat-conflict.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
              draft_present: false,
              pending_attachment: null,
              pending_review: null,
            }),
          },
          cvManager: {
            fetchCvManager,
            getProfileReextractOperation,
            getProfileReextractReview,
            streamProfileReextract: startReextract,
          },
        }}
      />
    </Theme>,
  );
  return {profile, fetchCvManager};
}

describe('App foundation shell', () => {
  it('disables both CV upload controls while re-extraction is loading before operation recovery', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const profile = appProfile('11111111-1111-4111-8111-111111111111', true);
    const extractionStream = deferred<void>();
    const streamProfileReextract = vi.fn().mockReturnValue(extractionStream.promise);

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [profile],
                active_profile_id: profile.id,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [appConversation('loading-conversation', profile.id)],
                next_cursor: null,
              }),
            },
            chat: {loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null})},
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue({
                present: true,
                profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
                preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
                active_attachment: {id: 'attachment-loading', original_name: 'loading.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
                draft_present: false,
                pending_attachment: null,
                pending_review: null,
              }),
            },
            cvManager: {
              fetchCvManager: vi.fn().mockResolvedValue({items: []}),
              streamProfileReextract,
            },
          }}
        />
      </Theme>,
    );

    await userEvent.click(await screen.findByRole('button', {name: `Actions for ${profile.display_name}`}));
    await userEvent.click(await screen.findByRole('menuitem', {name: 'Re-extract CV'}));
    await screen.findByTestId('jobagent-profile-reextract-progress');
    expect(streamProfileReextract).toHaveBeenCalledWith(profile.id, expect.any(Object), expect.any(AbortSignal));

    expect(await screen.findByTestId('jobagent-cv-upload')).toBeDisabled();
    expect(await screen.findByTestId('jobagent-chat-pdf-upload')).toBeDisabled();
  });

  it('disables both CV upload controls while the recovered re-extraction operation is running', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const profile = appProfile('11111111-1111-4111-8111-111111111111', true);
    const runningOperation = {
      profile_id: profile.id,
      operation_id: '11111111-1111-4111-8111-111111111111',
      state: 'running' as const,
      error_code: null,
      error_summary: null,
      review_revision: null,
      can_review: false,
      can_retry: false,
      can_discard: false,
    };

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [profile],
                active_profile_id: profile.id,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [appConversation('running-conversation', profile.id)],
                next_cursor: null,
              }),
            },
            chat: {loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null})},
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue({
                present: true,
                profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
                preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
                active_attachment: {id: 'attachment-running', original_name: 'running.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
                draft_present: false,
                pending_attachment: null,
                pending_review: null,
              }),
              cvManager: {
                getProfileReextractOperation: vi.fn().mockResolvedValue({operation: runningOperation}),
              },
            },
          }}
        />
      </Theme>,
    );

    const sidebarUpload = await screen.findByTestId('jobagent-cv-upload');
    const chatUpload = await screen.findByTestId('jobagent-chat-pdf-upload');
    await waitFor(() => {
      expect(sidebarUpload).toBeDisabled();
      expect(chatUpload).toBeDisabled();
    });
  });

  it('does not present a different operation after an upload conflict names an exact operation', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const profile = appProfile('11111111-1111-4111-8111-111111111111', true);
    const conflictOperationId = '22222222-2222-4222-8222-222222222222';
    const returnedOperationId = '33333333-3333-4333-8333-333333333333';
    const getProfileReextractOperation = vi
      .fn()
      .mockResolvedValueOnce({operation: null})
      .mockResolvedValueOnce({
        operation: {
          profile_id: profile.id,
          operation_id: returnedOperationId,
          state: 'running' as const,
          error_code: null,
          error_summary: null,
          review_revision: null,
          can_review: false,
          can_retry: false,
          can_discard: false,
        },
      });

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [profile],
                active_profile_id: profile.id,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [appConversation('conflict-conversation', profile.id)],
                next_cursor: null,
              }),
            },
            chat: {loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null})},
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue({
                present: true,
                profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
                preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
                active_attachment: {id: 'attachment-conflict', original_name: 'conflict.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
                draft_present: false,
                pending_attachment: null,
                pending_review: null,
              }),
              uploadCv: vi.fn().mockRejectedValue(Object.assign(
                new ChatApiError(409, 'PROFILE_REEXTRACT_IN_PROGRESS', 'A re-extraction is already running'),
                {detail: {code: 'PROFILE_REEXTRACT_IN_PROGRESS', summary: 'A re-extraction is already running', profile_id: profile.id, operation_id: conflictOperationId}},
              )),
              cvManager: {
                fetchCvManager: vi.fn().mockResolvedValue({items: []}),
                getProfileReextractOperation,
              },
            },
          }}
        />
      </Theme>,
    );

    await userEvent.upload(
      await screen.findByTestId('jobagent-cv-upload'),
      new File(['%PDF-1.4'], 'conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Check re-extraction'}));

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog', {name: 'CV Manager'})).not.toBeInTheDocument();
  });

  it('recovers one structured re-extraction conflict operation and never starts another extraction', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const getProfileReextractOperation = vi.fn()
      .mockResolvedValueOnce({operation: null})
      .mockResolvedValue({operation: {
        profile_id: CONFLICT_PROFILE_ID,
        operation_id: CONFLICT_OPERATION_ID,
        state: 'review_ready' as const,
        error_code: null,
        error_summary: null,
        review_revision: CONFLICT_REVISION,
        can_review: true,
        can_retry: false,
        can_discard: true,
      }});
    const getProfileReextractReview = vi.fn().mockResolvedValue(
      reextractReview(CONFLICT_PROFILE_ID, CONFLICT_OPERATION_ID, 'reextract'),
    );
    const startReextract = vi.fn();
    const {profile, fetchCvManager} = renderUploadConflictApp(
      {code: 'PROFILE_REVIEW_PENDING', summary: 'Review pending', profile_id: CONFLICT_PROFILE_ID, review_source: 'reextract', operation_id: CONFLICT_OPERATION_ID, review_revision: CONFLICT_REVISION},
      getProfileReextractOperation,
      getProfileReextractReview,
      startReextract,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    getProfileReextractOperation.mockClear();
    fetchCvManager.mockClear();
    await userEvent.upload(
      await screen.findByTestId('jobagent-cv-upload'),
      new File(['%PDF-1.4'], 'conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Review changes'}));
    await screen.findByTestId('jobagent-profile-reextract-review');

    expect(getProfileReextractOperation).toHaveBeenCalledTimes(1);
    expect(fetchCvManager).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).toHaveBeenCalledWith(profile.id, expect.any(AbortSignal), CONFLICT_OPERATION_ID);
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('loads one structured ordinary review with its exact revision and never starts re-extraction', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const getProfileReextractOperation = vi.fn().mockResolvedValue({operation: null});
    const getProfileReextractReview = vi.fn().mockResolvedValue(
      reextractReview(CONFLICT_PROFILE_ID, null, 'agent_update'),
    );
    const startReextract = vi.fn();
    const {profile} = renderUploadConflictApp(
      {code: 'PROFILE_REVIEW_PENDING', summary: 'Review pending', profile_id: CONFLICT_PROFILE_ID, review_source: 'agent_update', operation_id: null, review_revision: CONFLICT_REVISION},
      getProfileReextractOperation,
      getProfileReextractReview,
      startReextract,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    getProfileReextractOperation.mockClear();
    await userEvent.upload(
      await screen.findByTestId('jobagent-cv-upload'),
      new File(['%PDF-1.4'], 'conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Review changes'}));
    await screen.findByTestId('jobagent-profile-reextract-review');

    expect(getProfileReextractOperation).not.toHaveBeenCalled();
    expect(getProfileReextractReview).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).toHaveBeenCalledWith(profile.id, undefined);
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('opens the exact running operation after a Chat-originated in-progress conflict', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const getProfileReextractOperation = vi.fn()
      .mockResolvedValueOnce({operation: null})
      .mockResolvedValue({operation: {
        profile_id: CONFLICT_PROFILE_ID,
        operation_id: CONFLICT_OPERATION_ID,
        state: 'running' as const,
        error_code: null,
        error_summary: null,
        review_revision: null,
        can_review: false,
        can_retry: false,
        can_discard: false,
      }});
    const getProfileReextractReview = vi.fn();
    const startReextract = vi.fn();
    const {profile, fetchCvManager} = renderChatConflictApp(
      {code: 'PROFILE_REEXTRACT_IN_PROGRESS', summary: 'A re-extraction is already running', profile_id: CONFLICT_PROFILE_ID, operation_id: CONFLICT_OPERATION_ID},
      getProfileReextractOperation,
      getProfileReextractReview,
      startReextract,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    getProfileReextractOperation.mockClear();
    fetchCvManager.mockClear();
    await userEvent.upload(
      await screen.findByTestId('jobagent-chat-pdf-upload'),
      new File(['%PDF-1.4'], 'chat-conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Check re-extraction'}));
    await screen.findByRole('dialog', {name: 'CV Manager'});

    expect(getProfileReextractOperation).toHaveBeenCalledTimes(1);
    expect(fetchCvManager).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).not.toHaveBeenCalled();
    expect(startReextract).not.toHaveBeenCalled();
    expect(profile.id).toBe(CONFLICT_PROFILE_ID);
  });

  it('opens the exact re-extraction review after a Chat-originated pending conflict', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const getProfileReextractOperation = vi.fn()
      .mockResolvedValueOnce({operation: null})
      .mockResolvedValue({operation: {
        profile_id: CONFLICT_PROFILE_ID,
        operation_id: CONFLICT_OPERATION_ID,
        state: 'review_ready' as const,
        error_code: null,
        error_summary: null,
        review_revision: CONFLICT_REVISION,
        can_review: true,
        can_retry: false,
        can_discard: true,
      }});
    const getProfileReextractReview = vi.fn().mockResolvedValue(
      reextractReview(CONFLICT_PROFILE_ID, CONFLICT_OPERATION_ID, 'reextract'),
    );
    const startReextract = vi.fn();
    const {profile, fetchCvManager} = renderChatConflictApp(
      {code: 'PROFILE_REVIEW_PENDING', summary: 'Review pending', profile_id: CONFLICT_PROFILE_ID, review_source: 'reextract', operation_id: CONFLICT_OPERATION_ID, review_revision: CONFLICT_REVISION},
      getProfileReextractOperation,
      getProfileReextractReview,
      startReextract,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    getProfileReextractOperation.mockClear();
    fetchCvManager.mockClear();
    await userEvent.upload(
      await screen.findByTestId('jobagent-chat-pdf-upload'),
      new File(['%PDF-1.4'], 'chat-conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Review changes'}));
    await screen.findByRole('dialog', {name: 'CV Manager'});
    await screen.findByTestId('jobagent-profile-reextract-review');

    expect(getProfileReextractOperation).toHaveBeenCalledTimes(1);
    expect(fetchCvManager).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).toHaveBeenCalledWith(profile.id, expect.any(AbortSignal), CONFLICT_OPERATION_ID);
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('opens the exact ordinary review after a Chat-originated agent-update conflict', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const getProfileReextractOperation = vi.fn().mockResolvedValue({operation: null});
    const getProfileReextractReview = vi.fn().mockResolvedValue(
      reextractReview(CONFLICT_PROFILE_ID, null, 'agent_update'),
    );
    const startReextract = vi.fn();
    const {profile, fetchCvManager} = renderChatConflictApp(
      {code: 'PROFILE_REVIEW_PENDING', summary: 'Review pending', profile_id: CONFLICT_PROFILE_ID, review_source: 'agent_update', operation_id: null, review_revision: CONFLICT_REVISION},
      getProfileReextractOperation,
      getProfileReextractReview,
      startReextract,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    getProfileReextractOperation.mockClear();
    fetchCvManager.mockClear();
    await userEvent.upload(
      await screen.findByTestId('jobagent-chat-pdf-upload'),
      new File(['%PDF-1.4'], 'chat-conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Review changes'}));
    await screen.findByRole('dialog', {name: 'CV Manager'});
    await screen.findByTestId('jobagent-profile-reextract-review');

    expect(getProfileReextractOperation).not.toHaveBeenCalled();
    expect(fetchCvManager).not.toHaveBeenCalled();
    expect(getProfileReextractReview).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).toHaveBeenCalledWith(profile.id, undefined);
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('discards a deferred Chat operation presentation when the active profile switches before consumption', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const oldProfile = appProfile(CONFLICT_PROFILE_ID, true);
    const switchedProfile = appProfile(SWITCHED_PROFILE_ID, false);
    const oldConversation = appConversation('old-chat-conversation', oldProfile.id);
    const switchedConversation = appConversation('switched-chat-conversation', switchedProfile.id);
    const operationDeferred = deferred<{operation: {
      profile_id: string;
      operation_id: string;
      state: 'running';
      error_code: null;
      error_summary: null;
      review_revision: null;
      can_review: false;
      can_retry: false;
      can_discard: false;
    } | null}>();
    const getProfileReextractOperation = vi.fn()
      .mockResolvedValueOnce({operation: null})
      .mockImplementationOnce(() => operationDeferred.promise)
      .mockResolvedValue({operation: null});
    const getProfileReextractReview = vi.fn();
    const startReextract = vi.fn();
    const fetchCvManager = vi.fn().mockResolvedValue({items: []});
    const loadProfile = vi.fn().mockResolvedValue({
      present: true,
      profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
      preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
      active_attachment: {id: 'attachment-chat-conflict', original_name: 'chat-conflict.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
      draft_present: false,
      pending_attachment: null,
      pending_review: null,
    });
    const chat = {
      loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
      uploadCv: vi.fn().mockRejectedValue(new ChatApiError(409, 'PROFILE_REEXTRACT_IN_PROGRESS', 'A re-extraction is already running', {
        code: 'PROFILE_REEXTRACT_IN_PROGRESS',
        summary: 'A re-extraction is already running',
        profile_id: oldProfile.id,
        operation_id: CONFLICT_OPERATION_ID,
      })),
    };
    const cvManager = {fetchCvManager, getProfileReextractOperation, getProfileReextractReview, streamProfileReextract: startReextract};
    const initialWorkspace = {
      fetchProfiles: vi.fn().mockResolvedValue({items: [oldProfile, switchedProfile], active_profile_id: oldProfile.id}),
      fetchProfileConversations: vi.fn().mockResolvedValue({items: [oldConversation], next_cursor: null}),
    };
    const switchedWorkspace = {
      fetchProfiles: vi.fn().mockResolvedValue({items: [{...oldProfile, is_active: false}, {...switchedProfile, is_active: true}], active_profile_id: switchedProfile.id}),
      fetchProfileConversations: vi.fn().mockResolvedValue({items: [switchedConversation], next_cursor: null}),
    };
    const initialDeps = {workspace: initialWorkspace, chat, sidebar: {loadProfile}, cvManager};
    const switchedDeps = {workspace: switchedWorkspace, chat, sidebar: {loadProfile}, cvManager};
    const {rerender} = render(
      <Theme theme={neutralTheme}><App deps={initialDeps} /></Theme>,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(1));
    await userEvent.upload(
      await screen.findByTestId('jobagent-chat-pdf-upload'),
      new File(['%PDF-1.4'], 'chat-conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Check re-extraction'}));
    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(2));

    await act(async () => {
      operationDeferred.resolve({operation: {
        profile_id: oldProfile.id,
        operation_id: CONFLICT_OPERATION_ID,
        state: 'running',
        error_code: null,
        error_summary: null,
        review_revision: null,
        can_review: false,
        can_retry: false,
        can_discard: false,
      }});
      await Promise.resolve();
      rerender(<Theme theme={neutralTheme}><App deps={switchedDeps} /></Theme>);
    });

    await waitFor(() => expect(switchedWorkspace.fetchProfiles).toHaveBeenCalled());
    expect(screen.queryByRole('dialog', {name: 'CV Manager'})).not.toBeInTheDocument();
    rerender(<Theme theme={neutralTheme}><App deps={initialDeps} /></Theme>);
    await waitFor(() => expect(initialWorkspace.fetchProfiles).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog', {name: 'CV Manager'})).not.toBeInTheDocument();
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('discards a deferred Chat ordinary-review presentation after a profile switch and remount', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const oldProfile = appProfile(CONFLICT_PROFILE_ID, true);
    const switchedProfile = appProfile(SWITCHED_PROFILE_ID, false);
    const oldConversation = appConversation('old-review-conversation', oldProfile.id);
    const switchedConversation = appConversation('switched-review-conversation', switchedProfile.id);
    const reviewDeferred = deferred<ReturnType<typeof reextractReview>>();
    const getProfileReextractOperation = vi.fn().mockResolvedValue({operation: null});
    const getProfileReextractReview = vi.fn().mockImplementationOnce(() => reviewDeferred.promise);
    const startReextract = vi.fn();
    const loadProfile = vi.fn().mockResolvedValue({
      present: true,
      profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
      preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
      active_attachment: {id: 'attachment-chat-review', original_name: 'chat-review.pdf', mime_type: 'application/pdf', size_bytes: 1, page_count: 1, state: 'active', failure_code: null},
      draft_present: false,
      pending_attachment: null,
      pending_review: null,
    });
    const chat = {
      loadConversationHistory: vi.fn().mockResolvedValue({items: [], next_cursor: null}),
      uploadCv: vi.fn().mockRejectedValue(new ChatApiError(409, 'PROFILE_REVIEW_PENDING', 'Review pending', {
        code: 'PROFILE_REVIEW_PENDING',
        summary: 'Review pending',
        profile_id: oldProfile.id,
        review_source: 'agent_update',
        operation_id: null,
        review_revision: CONFLICT_REVISION,
      })),
    };
    const cvManager = {getProfileReextractOperation, getProfileReextractReview, streamProfileReextract: startReextract};
    const initialWorkspace = {
      fetchProfiles: vi.fn().mockResolvedValue({items: [oldProfile, switchedProfile], active_profile_id: oldProfile.id}),
      fetchProfileConversations: vi.fn().mockResolvedValue({items: [oldConversation], next_cursor: null}),
    };
    const switchedWorkspace = {
      fetchProfiles: vi.fn().mockResolvedValue({items: [{...oldProfile, is_active: false}, {...switchedProfile, is_active: true}], active_profile_id: switchedProfile.id}),
      fetchProfileConversations: vi.fn().mockResolvedValue({items: [switchedConversation], next_cursor: null}),
    };
    const initialDeps = {workspace: initialWorkspace, chat, sidebar: {loadProfile}, cvManager};
    const switchedDeps = {workspace: switchedWorkspace, chat, sidebar: {loadProfile}, cvManager};
    const {rerender} = render(
      <Theme theme={neutralTheme}><App deps={initialDeps} /></Theme>,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    await userEvent.upload(
      await screen.findByTestId('jobagent-chat-pdf-upload'),
      new File(['%PDF-1.4'], 'chat-review.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Review changes'}));
    await waitFor(() => expect(getProfileReextractReview).toHaveBeenCalledTimes(1));

    await act(async () => {
      reviewDeferred.resolve(reextractReview(oldProfile.id, null, 'agent_update'));
      await Promise.resolve();
      rerender(<Theme theme={neutralTheme}><App deps={switchedDeps} /></Theme>);
    });

    await waitFor(() => expect(switchedWorkspace.fetchProfiles).toHaveBeenCalled());
    expect(screen.queryByRole('dialog', {name: 'CV Manager'})).not.toBeInTheDocument();
    rerender(<Theme theme={neutralTheme}><App deps={initialDeps} /></Theme>);
    await waitFor(() => expect(initialWorkspace.fetchProfiles).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog', {name: 'CV Manager'})).not.toBeInTheDocument();
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('keeps the drawer closed after a Chat-originated operation mismatch', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const returnedOperationId = '33333333-3333-4333-8333-333333333333';
    const getProfileReextractOperation = vi.fn()
      .mockResolvedValueOnce({operation: null})
      .mockResolvedValue({operation: {
        profile_id: CONFLICT_PROFILE_ID,
        operation_id: returnedOperationId,
        state: 'running' as const,
        error_code: null,
        error_summary: null,
        review_revision: null,
        can_review: false,
        can_retry: false,
        can_discard: false,
      }});
    const getProfileReextractReview = vi.fn();
    const startReextract = vi.fn();
    const {fetchCvManager} = renderChatConflictApp(
      {code: 'PROFILE_REEXTRACT_IN_PROGRESS', summary: 'A re-extraction is already running', profile_id: CONFLICT_PROFILE_ID, operation_id: CONFLICT_OPERATION_ID},
      getProfileReextractOperation,
      getProfileReextractReview,
      startReextract,
    );

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalled());
    getProfileReextractOperation.mockClear();
    fetchCvManager.mockClear();
    await userEvent.upload(
      await screen.findByTestId('jobagent-chat-pdf-upload'),
      new File(['%PDF-1.4'], 'chat-conflict.pdf', {type: 'application/pdf'}),
    );
    await userEvent.click(await screen.findByRole('button', {name: 'Check re-extraction'}));
    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(1));

    expect(fetchCvManager).toHaveBeenCalledTimes(1);
    expect(getProfileReextractReview).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', {name: 'CV Manager'})).not.toBeInTheDocument();
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('retains only a selected scorable Job for fresh tailoring recovery', () => {
    const job = {
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Synthetic job',
      company: 'Synthetic Co',
      display_label: 'Synthetic job · Synthetic Co',
      processing_status: 'processed' as const,
      jd_quality: 'full' as const,
      source_type: 'text' as const,
      source_url: null,
      created_at: '2026-07-26T00:00:00Z',
      updated_at: '2026-07-26T00:00:00Z',
      evaluation_state: 'current' as const,
      latest_score: null,
    };
    expect(
      selectedScorableJobId({
        selectedJobId: job.id,
        list: {
          phase: 'ready',
          data: {items: [job], next_cursor: null},
          error: null,
          loaded: true,
        },
      }),
    ).toBe(job.id);
    expect(
      selectedScorableJobId({
        selectedJobId: job.id,
        list: {
          phase: 'ready',
          data: {
            items: [{...job, jd_quality: 'unscorable'}],
            next_cursor: null,
          },
          error: null,
          loaded: true,
        },
      }),
    ).toBeNull();

    const selectedState = {
      selectedJobId: job.id,
      list: {
        phase: 'ready' as const,
        data: {items: [job], next_cursor: null},
        error: null,
        loaded: true,
      },
    };
    expect(freshTailoringRequest(selectedState, '   ')).toEqual({
      job_id: job.id,
      instruction: '',
    });
    expect(
      freshTailoringRequest(
        {
          ...selectedState,
          list: {
            ...selectedState.list,
            data: {
              items: [{...job, jd_quality: 'unscorable' as const}],
              next_cursor: null,
            },
          },
        },
        '  Focus on evidence  ',
      ),
    ).toEqual({job_id: null, instruction: 'Focus on evidence'});
    expect(
      freshTailoringRequest(
        {
          ...selectedState,
          list: {
            ...selectedState.list,
            data: {
              items: [{...job, jd_quality: 'unscorable' as const}],
              next_cursor: null,
            },
          },
        },
        '   ',
      ),
    ).toBeNull();
  });

  it('reloads the latest parent while preserving the local tailoring draft', async () => {
    const draft = {
      header: {
        full_name: 'Synthetic Candidate',
        location: null,
        phone: null,
        email: null,
        github_url: null,
      },
      sections: [],
    };
    const openSession = vi.fn().mockResolvedValue(true);
    const setDraft = vi.fn();

    expect(
      await reloadLatestTailoring({
        state: {
          selectedSessionId: '11111111-1111-4111-8111-111111111111',
          draft,
        },
        openSession,
        setDraft,
      }),
    ).toBe(true);
    expect(openSession).toHaveBeenCalledWith(
      '11111111-1111-4111-8111-111111111111',
    );
    expect(setDraft).toHaveBeenCalledWith(draft);
  });

  it('renders AppShell with CV sidebar and chat page', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    window.localStorage.removeItem(
      'astryx-resizable:jobagent-product-workspace-panel-width-v1',
    );
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/profiles')) {
        return new Response(
          JSON.stringify({items: [], active_profile_id: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.includes('/api/profile') && !url.includes('/cv')) {
        return new Response(
          JSON.stringify({
            present: false,
            profile: null,
            preferences: null,
            active_attachment: null,
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      return new Response(JSON.stringify({items: [], next_cursor: null}), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      });
    });

    const {container} = render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    const workspacePanel = await screen.findByTestId(
      'jobagent-product-workspace-panel',
    );
    expect(workspacePanel).toHaveClass('jobagent-hidden-scrollbar');
    expect(screen.getByTestId('jobagent-product-workspace')).toHaveClass(
      'jobagent-hidden-scrollbar',
    );
    const resizeHandle = screen.getByRole('separator', {
      name: 'Resize workspace panel',
    });
    expect(resizeHandle).toHaveAttribute('aria-valuenow', '420');
    expect(resizeHandle).toHaveAttribute('aria-valuemin', '320');
    expect(resizeHandle).toHaveAttribute('aria-valuemax', '720');
    expect(await screen.findByTestId('jobagent-chat-page')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-cv-sidebar')).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText(/Start a conversation|History load issue/),
      ).toBeInTheDocument();
    });
  });

  it('removes stale chat while a non-persisted pageshow reloads and remounts for the new identities', async () => {
    const first = deferred<ProfileListResponse>();
    const second = deferred<ProfileListResponse>();
    const profileA = appProfile('profile-a', true);
    const profileB = appProfile('profile-b', true);
    const conversationA = appConversation('conversation-a', profileA.id);
    const conversationB = appConversation('conversation-b', profileB.id);
    let profileRequest = 0;
    const fetchProfiles = vi.fn(() =>
      [first.promise, second.promise][profileRequest++],
    );
    const fetchProfileConversations = vi.fn((profileId: string) =>
      Promise.resolve({
        items: [profileId === profileA.id ? conversationA : conversationB],
        next_cursor: null,
      }),
    );
    const loadConversationHistory = vi.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
    });

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/profiles')) {
        return new Response(
          JSON.stringify({items: [], active_profile_id: null}),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      if (url.includes('/api/profile') && !url.includes('/cv')) {
        return new Response(
          JSON.stringify({
            present: false,
            profile: null,
            preferences: null,
            active_attachment: null,
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      return new Response(JSON.stringify({items: [], next_cursor: null}), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      });
    });

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {fetchProfiles, fetchProfileConversations},
            chat: {loadConversationHistory},
          }}
        />
      </Theme>,
    );

    expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();
    first.resolve({items: [profileA], active_profile_id: profileA.id});
    await waitFor(() => expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument());
    await waitFor(() => expect(loadConversationHistory).toHaveBeenCalledTimes(1));

    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: false}));
    });
    await waitFor(() => expect(fetchProfiles).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();

    second.resolve({items: [profileB], active_profile_id: profileB.id});
    await waitFor(() => expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument());
    await waitFor(() => expect(loadConversationHistory).toHaveBeenCalledTimes(2));
    expect(loadConversationHistory.mock.calls.map(([id]) => id)).toEqual([
      conversationA.id,
      conversationB.id,
    ]);
  });

  it('switches to a validated tailoring workspace without remounting ChatPage', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://api.example.test');
    const profileId = '11111111-1111-4111-8111-111111111111';
    const conversationId = '22222222-2222-4222-8222-222222222222';
    const sessionId = '33333333-3333-4333-8333-333333333333';
    const versionId = '44444444-4444-4444-8444-444444444444';
    const timestamp = '2026-07-26T00:00:00Z';
    const profile = {
      id: profileId,
      display_name: 'Synthetic CV',
      cv_filename: 'synthetic.pdf',
      attachment_state: 'active',
      location: null,
      skill_tags: [],
      skill_count: 0,
      extraction_version: 'v1',
      source_hash: 'hash',
      state: 'ready' as const,
      setup_status: null,
      is_active: true,
      created_at: timestamp,
      updated_at: timestamp,
      last_opened_at: timestamp,
    };
    const loadConversationHistory = vi.fn().mockResolvedValue({
      items: [
        {
          id: '55555555-5555-4555-8555-555555555555',
          role: 'user',
          content: 'Tailor CV',
          structured_payload: null,
          created_at: timestamp,
          updated_at: timestamp,
          run: {
            id: '66666666-6666-4666-8666-666666666666',
            user_message_id: '55555555-5555-4555-8555-555555555555',
            state: 'completed',
            pending_approval: null,
            error_code: null,
            completed_at: timestamp,
            created_at: timestamp,
            updated_at: timestamp,
            activities: [],
            tool_executions: [
              {
                id: '77777777-7777-4777-8777-777777777777',
                tool_call_id: 'tool-call',
                tool_name: 'create_tailored_cv',
                status: 'completed',
                duration_ms: 1,
                error_code: null,
                created_at: timestamp,
                updated_at: timestamp,
                arguments_summary: null,
                result: {
                  ok: true,
                  code: null,
                  summary: 'ready',
                  data: {outcome: 'version_created', session_id: sessionId, version_id: versionId, status: 'ready', currentness: 'current'},
                },
              },
            ],
          },
        },
        {
          id: '88888888-8888-4888-8888-888888888888',
          role: 'assistant',
          content: 'Your tailored CV is ready.',
          structured_payload: null,
          created_at: timestamp,
          updated_at: timestamp,
          run: null,
        },
      ],
      next_cursor: null,
    });

    const fetchSession = vi.fn().mockResolvedValue({
      session: {
        id: sessionId,
        profile_id: profileId,
        job_label: null,
        instruction: 'Focus on verified evidence',
        template_version: 'latex-cv-v1',
        state: 'ready',
        currentness: 'current',
        latest_version_number: 1,
        error_code: null,
        created_at: timestamp,
        updated_at: timestamp,
      },
      versions: [
        {
          id: versionId,
          version_number: 1,
          parent_version_id: null,
          created_by: 'ai',
          page_count: 1,
          page_warning: null,
          created_at: timestamp,
        },
      ],
      selected_version: {
        id: versionId,
        version_number: 1,
        parent_version_id: null,
        created_by: 'ai',
        page_count: 1,
        page_warning: null,
        created_at: timestamp,
      },
      content: {
        header: {
          full_name: 'Synthetic Candidate',
          location: null,
          phone: null,
          email: null,
          github_url: null,
        },
        sections: [
          {
            id: 'summary',
            ordinal: 0,
            heading: 'Summary',
            kind: 'summary',
            items: [],
          },
        ],
      },
      evidence: [],
      latest_run: null,
      source_available: true,
      pdf_available: true,
    });
    const streamProfileReextract = vi.fn().mockResolvedValue(undefined);
    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            workspace: {
              fetchProfiles: vi.fn().mockResolvedValue({
                items: [profile],
                active_profile_id: profileId,
              }),
              fetchProfileConversations: vi.fn().mockResolvedValue({
                items: [{id: conversationId, profile_id: profileId, title: 'Chat', created_at: timestamp, updated_at: timestamp, last_opened_at: timestamp, is_selected: true}],
                next_cursor: null,
              }),
            },
            chat: {loadConversationHistory},
            tailoring: {fetchSession},
            sidebar: {
              loadProfile: vi.fn().mockResolvedValue({
                present: true,
                profile: {summary: 'Synthetic candidate', current_title: 'Engineer'},
                preferences: {target_roles: [], preferred_locations: [], acceptable_work_modes: [], target_seniority: []},
                active_attachment: {id: versionId, original_name: 'synthetic.pdf', mime_type: 'application/pdf', size_bytes: 1024, page_count: 1, state: 'active', failure_code: null},
                draft_present: false,
                pending_attachment: null,
              }),
              cvManager: {
                fetchCvManager: vi.fn().mockResolvedValue({items: []}),
                streamProfileReextract,
                getProfileReextractReview: vi.fn().mockRejectedValue(new Error('review not ready')),
              },
            },
          }}
        />
      </Theme>,
    );

    const openEditor = await screen.findByRole('button', {name: 'Open tailored CV'});
    const chat = screen.getByTestId('jobagent-chat-page');
    await userEvent.click(openEditor);
    await waitFor(() => {
      expect(fetchSession).toHaveBeenCalledWith(sessionId, undefined, expect.any(AbortSignal));
    });
    expect(
      screen.getByRole('heading', {level: 1, name: 'Tailored CV'}),
    ).toBeInTheDocument();
    const hiddenChatWorkspace = chat.closest('[hidden]');
    expect(hiddenChatWorkspace).not.toBeNull();
    expect(hiddenChatWorkspace).toHaveClass('jobagent-chat-workspace');
    expect(getComputedStyle(hiddenChatWorkspace as HTMLElement).display).toBe(
      'none',
    );
    expect(screen.getByTestId('jobagent-chat-page')).toBe(chat);
    expect(loadConversationHistory).toHaveBeenCalledTimes(1);
    await userEvent.click(
      screen.getByRole('button', {name: 'Edit profile information'}),
    );
    await waitFor(() => expect(streamProfileReextract).toHaveBeenCalledWith(profileId, expect.any(Object), expect.any(AbortSignal)));
    expect(screen.getByRole('heading', {level: 1, name: 'Tailored CV'})).toBeInTheDocument();
    expect(screen.getByRole('dialog', {name: 'CV Manager'})).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', {name: 'Back to chat'}),
    );
    await waitFor(() => {
      expect(
        screen.queryByRole('heading', {level: 1, name: 'Tailored CV'}),
      ).not.toBeInTheDocument();
      expect(chat.closest('[hidden]')).toBeNull();
    });
    expect(screen.getByTestId('jobagent-chat-page')).toBe(chat);
  });

  it('closes tailoring when the workspace profile changes and blocks stale opens', async () => {
    const first = deferred<ProfileListResponse>();
    const second = deferred<ProfileListResponse>();
    const staleSession = deferred<TailoringSessionDetailResponse>();
    const profileA = appProfile('profile-a', true);
    const profileB = appProfile('profile-b', true);
    const conversationA = appConversation('conversation-a', profileA.id);
    const conversationB = appConversation('conversation-b', profileB.id);
    const sessionId = '33333333-3333-4333-8333-333333333333';
    const timestamp = '2026-07-28T00:00:00Z';
    const session = {
      id: sessionId,
      profile_id: profileA.id,
      job_label: null,
      instruction: 'Focus on verified evidence',
      template_version: 'latex-cv-v1' as const,
      state: 'ready' as const,
      currentness: 'current' as const,
      latest_version_number: 0,
      error_code: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    const detail = (profileId: string): TailoringSessionDetailResponse => ({
      session: {...session, profile_id: profileId},
      versions: [],
      selected_version: null,
      content: {
        header: {
          full_name: 'Synthetic Candidate',
          location: null,
          phone: null,
          email: null,
          github_url: null,
        },
        sections: [],
      },
      evidence: [],
      latest_run: null,
      fit_warning: null,
      source_available: false,
      pdf_available: false,
    });
    const fetchProfiles = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const fetchProfileConversations = vi.fn((profileId: string) =>
      Promise.resolve({
        items: [profileId === profileA.id ? conversationA : conversationB],
        next_cursor: null,
      }),
    );
    const loadConversationHistory = vi.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const fetchSessions = vi.fn().mockResolvedValue({items: [session]});
    const fetchSession = vi
      .fn()
      .mockResolvedValueOnce(detail(profileA.id))
      .mockImplementationOnce(() => staleSession.promise);
    const workspace = {fetchProfiles, fetchProfileConversations};
    const chat = {loadConversationHistory};
    const tailoring = {fetchSessions, fetchSession};

    render(
      <Theme theme={neutralTheme}>
        <App deps={{workspace, chat, tailoring}} />
      </Theme>,
    );

    first.resolve({items: [profileA], active_profile_id: profileA.id});
    await waitFor(() =>
      expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole('button', {name: 'Tailored CVs'}),
    );
    const sessionRow = await screen.findByTestId(
      'jobagent-tailoring-session-' + sessionId,
    );
    await userEvent.click(sessionRow);
    await waitFor(() =>
      expect(screen.getByRole('heading', {level: 1})).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole('button', {name: 'Back to chat'}));
    const reopenedSessionRow = await screen.findByTestId(
      'jobagent-tailoring-session-' + sessionId,
    );
    await userEvent.click(reopenedSessionRow);
    await waitFor(() => expect(fetchSession).toHaveBeenCalledTimes(2));

    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
    });
    await waitFor(() => expect(fetchProfiles).toHaveBeenCalledTimes(2));
    expect(
      screen.queryByRole('heading', {level: 1}),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();

    second.resolve({items: [profileB], active_profile_id: profileB.id});
    await waitFor(() =>
      expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument(),
    );
    staleSession.resolve(detail(profileA.id));
    await waitFor(() => expect(fetchSession).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('heading', {level: 1})).not.toBeInTheDocument();
    expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument();
  });
});

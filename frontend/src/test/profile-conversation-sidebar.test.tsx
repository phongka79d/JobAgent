import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ConversationListPanel} from '../features/profile/ConversationListPanel';
import {ProfileConversationSidebar} from '../features/profile/ProfileConversationSidebar';
import {ProfileListPanel} from '../features/profile/ProfileListPanel';
import type {
  ConversationSummary,
  ProfileListItem,
} from '../features/profile/conversationTypes';

const PROFILE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const PENDING_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const CONVERSATION_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const NOW = '2026-07-24T06:00:00Z';

const readyProfile: ProfileListItem = {
  id: PROFILE_ID,
  display_name: 'Ada Lovelace',
  cv_filename: 'ada-cv.pdf',
  attachment_state: 'active',
  location: 'Berlin',
  skill_tags: [
    {key: 'python', label: 'Python'},
    {key: 'sql', label: 'SQL'},
    {key: 'fastapi', label: 'FastAPI'},
    {key: 'react', label: 'React'},
  ],
  skill_count: 7,
  extraction_version: 'v1',
  source_hash: 'source-a',
  state: 'ready',
  setup_status: null,
  is_active: true,
  created_at: NOW,
  updated_at: NOW,
  last_opened_at: NOW,
};

const pendingProfile: ProfileListItem = {
  id: PENDING_ID,
  display_name: 'new-cv.pdf',
  cv_filename: 'new-cv.pdf',
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
};

const conversation: ConversationSummary = {
  id: CONVERSATION_ID,
  profile_id: PROFILE_ID,
  title: 'Platform role search',
  created_at: NOW,
  updated_at: NOW,
  last_opened_at: NOW,
  is_selected: true,
};

function themed(node: React.ReactNode) {
  return render(<Theme theme={neutralTheme}>{node}</Theme>);
}

afterEach(cleanup);

describe('profile and conversation navigation', () => {
  it('renders persisted location, bounded skill tokens, and overflow', () => {
    themed(
      <ProfileListPanel
        profiles={[
          readyProfile,
          {
            ...readyProfile,
            id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
            display_name: 'Metadata unavailable',
            location: null,
            skill_tags: [],
            skill_count: 0,
            is_active: false,
          },
        ]}
        activeProfileId={PROFILE_ID}
        isInteractionLocked={false}
        onActivate={vi.fn()}
        onRename={vi.fn()}
        onReextract={vi.fn()}
        onRetrySetup={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('Berlin')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('+3')).toBeInTheDocument();
    expect(screen.getByText('Location unavailable')).toBeInTheDocument();
    expect(screen.getByText('No extracted skills')).toBeInTheDocument();
  });

  it('renders pending setup status and exposes retry and discard only', async () => {
    const retry = vi.fn();
    const remove = vi.fn();
    themed(
      <ProfileListPanel
        profiles={[pendingProfile]}
        activeProfileId={PENDING_ID}
        isInteractionLocked={false}
        onActivate={vi.fn()}
        onRename={vi.fn()}
        onReextract={vi.fn()}
        onRetrySetup={retry}
        onDelete={remove}
      />,
    );

    expect(screen.getByText('Awaiting extraction')).toBeInTheDocument();
    expect(screen.getByText('Location unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /Rename/})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /Re-extract/})).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: /Retry/}));
    expect(retry).toHaveBeenCalledWith(pendingProfile);
    await userEvent.click(screen.getByRole('button', {name: /Discard/}));
    expect(remove).toHaveBeenCalledWith(pendingProfile);
  });

  it('renders ready conversations and creates one new chat for the selected profile', async () => {
    const create = vi.fn();
    themed(
      <ConversationListPanel
        profileId={PROFILE_ID}
        profileState="ready"
        conversations={[conversation]}
        selectedConversationId={CONVERSATION_ID}
        isInteractionLocked={false}
        onCreate={create}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('Platform role search')).toBeInTheDocument();
    expect(screen.getByText(/Last activity.*Jul.*2026/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'New chat'}));
    expect(create).toHaveBeenCalledWith(PROFILE_ID);
  });

  it('uses an icon-only action trigger for a long conversation title', () => {
    const title = 'Set preferred location to Da Nang and target role to Platform Engineer.';
    const actionName = `Actions for conversation ${title}`;
    themed(
      <ConversationListPanel
        profileId={PROFILE_ID}
        profileState="ready"
        conversations={[{...conversation, title}]}
        selectedConversationId={CONVERSATION_ID}
        isInteractionLocked={false}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', {name: actionName})).toHaveAttribute(
      'aria-label',
      actionName,
    );
  });

  it('keeps a pending bootstrap conversation read-only', () => {
    themed(
      <ConversationListPanel
        profileId={PENDING_ID}
        profileState="pending"
        conversations={[{...conversation, profile_id: PENDING_ID}]}
        selectedConversationId={CONVERSATION_ID}
        isInteractionLocked={false}
        onCreate={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', {name: 'New chat'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /Delete conversation/})).not.toBeInTheDocument();
  });

  it('disables ready profile and conversation actions while interaction is locked', () => {
    themed(
      <>
        <ProfileListPanel
          profiles={[readyProfile]}
          activeProfileId={PROFILE_ID}
          isInteractionLocked
          onActivate={vi.fn()}
          onRename={vi.fn()}
          onReextract={vi.fn()}
          onRetrySetup={vi.fn()}
          onDelete={vi.fn()}
        />
        <ConversationListPanel
          profileId={PROFILE_ID}
          profileState="ready"
          conversations={[conversation]}
          selectedConversationId={CONVERSATION_ID}
          isInteractionLocked
          onCreate={vi.fn()}
          onSelect={vi.fn()}
          onDelete={vi.fn()}
        />
      </>,
    );

    expect(screen.getByRole('button', {name: 'Actions for Ada Lovelace'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'New chat'})).toBeDisabled();
    expect(
      screen.getByRole('button', {name: 'Actions for conversation Platform role search'}),
    ).toHaveAttribute('aria-disabled', 'true');
  });

  it('does not expose ready or pending actions for a deleting profile', () => {
    themed(
      <ProfileListPanel
        profiles={[{
          ...readyProfile,
          attachment_state: 'deleting',
          state: 'deleting',
          is_active: false,
        }]}
        activeProfileId={null}
        isInteractionLocked={false}
        onActivate={vi.fn()}
        onRename={vi.fn()}
        onReextract={vi.fn()}
        onRetrySetup={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', {name: /Actions for/})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Retry'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Discard'})).not.toBeInTheDocument();
  });

  it('keeps profile deletion open and suppresses success callbacks on failure', async () => {
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    });
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function close() {
      this.removeAttribute('open');
    };
    const deleteProfile = vi.fn().mockResolvedValue(false);
    const onProfileDeleted = vi.fn();
    themed(
      <ProfileConversationSidebar
        workspace={{
          state: {
            profiles: [readyProfile],
            activeProfileId: PROFILE_ID,
            selectedConversationId: CONVERSATION_ID,
            conversations: [conversation],
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
        }}
        isInteractionLocked={false}
        onReextract={vi.fn()}
        onRetryUpload={vi.fn()}
        onProfileDeleted={onProfileDeleted}
      />,
    );

    await userEvent.click(screen.getByRole('button', {name: 'Actions for Ada Lovelace'}));
    await userEvent.click(await screen.findByText('Delete profile'));
    await userEvent.click(
      screen.getByRole('button', {name: 'Delete profile and all data'}),
    );

    await waitFor(() => expect(deleteProfile).toHaveBeenCalledWith(PROFILE_ID));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(onProfileDeleted).not.toHaveBeenCalled();
  });

  it('composes profile and conversation navigation from one workspace owner', () => {
    themed(
      <ProfileConversationSidebar
        workspace={{
          state: {
            profiles: [readyProfile],
            activeProfileId: PROFILE_ID,
            selectedConversationId: CONVERSATION_ID,
            conversations: [conversation],
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
        }}
        isInteractionLocked={false}
        onReextract={vi.fn()}
        onRetryUpload={vi.fn()}
      />,
    );

    expect(screen.getByTestId('jobagent-profile-list-panel')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-conversation-list-panel')).toBeInTheDocument();
  });
});

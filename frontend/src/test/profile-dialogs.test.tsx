import {useState} from 'react';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {ConversationDeleteDialog} from '../features/profile/ConversationDeleteDialog';
import {ProfileDeleteDialog} from '../features/profile/ProfileDeleteDialog';
import {ProfileRenameDialog} from '../features/profile/ProfileRenameDialog';
import type {
  ConversationSummary,
  ProfileListItem,
} from '../features/profile/conversationTypes';

const PROFILE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const CONVERSATION_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const NOW = '2026-07-24T06:00:00Z';

const profile: ProfileListItem = {
  id: PROFILE_ID,
  display_name: 'Ada Lovelace',
  cv_filename: 'ada-cv.pdf',
  attachment_state: 'active',
  location: 'Berlin',
  skill_tags: [],
  skill_count: 0,
  extraction_version: 'v1',
  source_hash: 'source-a',
  state: 'ready',
  setup_status: null,
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

function ConversationDeleteHarness({onConfirm}: {onConfirm: () => Promise<void>}) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setIsOpen(true)}>
        Open deletion
      </button>
      <ConversationDeleteDialog
        conversation={conversation}
        isOpen={isOpen}
        isActionLoading={false}
        onOpenChange={setIsOpen}
        onConfirm={onConfirm}
      />
    </>
  );
}

afterEach(cleanup);

beforeEach(() => {
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
});

describe('profile mutation dialogs', () => {
  it('submits exactly one display-name-only rename', async () => {
    const rename = vi.fn().mockResolvedValue(undefined);
    themed(
      <ProfileRenameDialog
        profile={profile}
        isOpen
        isActionLoading={false}
        onOpenChange={vi.fn()}
        onConfirm={rename}
      />,
    );

    const input = screen.getByRole('textbox', {name: /Profile name/});
    await userEvent.clear(input);
    await userEvent.type(input, 'Ada Byron');
    await userEvent.click(screen.getByRole('button', {name: 'Save name'}));
    await waitFor(() => expect(rename).toHaveBeenCalledTimes(1));
    expect(rename).toHaveBeenCalledWith(PROFILE_ID, 'Ada Byron');
  });

  it('names the profile and CV before permanent deletion', async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    themed(
      <ProfileDeleteDialog
        profile={profile}
        isOpen
        isActionLoading={false}
        onOpenChange={vi.fn()}
        onConfirm={remove}
      />,
    );

    expect(
      screen.getByRole('alertdialog', {name: 'Delete Ada Lovelace?'}),
    ).toBeInTheDocument();
    expect(screen.getByText(/ada-cv.pdf/)).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', {name: 'Delete permanently'}));
    expect(remove).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith(PROFILE_ID);
  });

  it('cancels conversation deletion without a request', async () => {
    const remove = vi.fn();
    const onOpenChange = vi.fn();
    themed(
      <ConversationDeleteDialog
        conversation={conversation}
        isOpen
        isActionLoading={false}
        onOpenChange={onOpenChange}
        onConfirm={remove}
      />,
    );

    expect(
      screen.getByRole('alertdialog', {
        name: 'Delete Platform role search?',
      }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(remove).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('performs one confirmed conversation delete request', async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    themed(
      <ConversationDeleteDialog
        conversation={conversation}
        isOpen
        isActionLoading={false}
        onOpenChange={vi.fn()}
        onConfirm={remove}
      />,
    );

    expect(remove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', {name: 'Delete permanently'}));
    expect(remove).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith(CONVERSATION_ID);
  });

  it('keeps the rename dialog open while its mutation is loading', async () => {
    const onOpenChange = vi.fn();
    themed(
      <ProfileRenameDialog
        profile={profile}
        isOpen
        isActionLoading
        onOpenChange={onOpenChange}
        onConfirm={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole('button', {name: 'Close'}));
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Rename profile'})).toBeInTheDocument();
  });

  it('closes on the Escape cancel path and restores focus to the opener', async () => {
    const remove = vi.fn();
    themed(<ConversationDeleteHarness onConfirm={remove} />);
    const opener = screen.getByRole('button', {name: 'Open deletion'});
    await userEvent.click(opener);
    const dialog = screen.getByRole('alertdialog');

    fireEvent(dialog, new Event('cancel', {bubbles: true, cancelable: true}));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
    expect(remove).not.toHaveBeenCalled();
  });
});

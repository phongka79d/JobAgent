import {useRef, useState} from 'react';
import {Banner} from '@astryxdesign/core/Banner';
import {Divider} from '@astryxdesign/core/Divider';
import {VStack} from '@astryxdesign/core/VStack';

import {ConversationDeleteDialog} from './ConversationDeleteDialog';
import {ConversationListPanel} from './ConversationListPanel';
import {ProfileDeleteDialog} from './ProfileDeleteDialog';
import {ProfileListPanel} from './ProfileListPanel';
import {ProfileRenameDialog} from './ProfileRenameDialog';
import type {
  ConversationSummary,
  ProfileListItem,
} from './conversationTypes';
import type {ProfileWorkspaceController} from './workspaceState';

export type ProfileConversationSidebarProps = {
  workspace: ProfileWorkspaceController;
  isInteractionLocked: boolean;
  onReextract: (profile: ProfileListItem) => void;
  onRetryUpload: (profile: ProfileListItem, file: File) => Promise<void>;
  onProfileDeleted?: () => void;
};

export function ProfileConversationSidebar({
  workspace,
  isInteractionLocked,
  onReextract,
  onRetryUpload,
  onProfileDeleted,
}: ProfileConversationSidebarProps) {
  const [renameTarget, setRenameTarget] = useState<ProfileListItem | null>(null);
  const [profileDeleteTarget, setProfileDeleteTarget] =
    useState<ProfileListItem | null>(null);
  const [conversationDeleteTarget, setConversationDeleteTarget] =
    useState<ConversationSummary | null>(null);
  const [retryTarget, setRetryTarget] = useState<ProfileListItem | null>(null);
  const retryInput = useRef<HTMLInputElement>(null);

  const selectedProfile =
    workspace.state.profiles.find(
      (profile) => profile.id === workspace.state.activeProfileId,
    ) ?? null;

  const requestRetryFile = (profile: ProfileListItem) => {
    setRetryTarget(profile);
    retryInput.current?.click();
  };

  return (
    <VStack gap={3} width="100%" data-testid="jobagent-profile-conversation-sidebar">
      {workspace.state.error ? (
        <Banner
          status="error"
          title="Workspace action failed"
          description={workspace.state.error}
          container="card"
        />
      ) : null}

      <ProfileListPanel
        profiles={workspace.state.profiles}
        activeProfileId={workspace.state.activeProfileId}
        isInteractionLocked={isInteractionLocked}
        onActivate={(profileId) => void workspace.activate(profileId)}
        onRename={setRenameTarget}
        onReextract={onReextract}
        onRetrySetup={requestRetryFile}
        onDelete={setProfileDeleteTarget}
      />

      <input
        ref={retryInput}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        aria-label="Retry profile CV"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0] ?? null;
          if (file && retryTarget) void onRetryUpload(retryTarget, file);
          event.currentTarget.value = '';
        }}
      />

      <Divider />

      <ConversationListPanel
        profileId={selectedProfile?.id ?? null}
        profileState={selectedProfile?.state ?? null}
        conversations={workspace.state.conversations}
        selectedConversationId={workspace.state.selectedConversationId}
        isInteractionLocked={isInteractionLocked}
        onCreate={(profileId) => void workspace.createConversation(profileId)}
        onSelect={(conversationId) =>
          void workspace.selectConversation(conversationId)
        }
        onDelete={setConversationDeleteTarget}
      />

      <ProfileRenameDialog
        profile={renameTarget}
        isOpen={renameTarget !== null}
        isActionLoading={isInteractionLocked}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(null);
        }}
        onConfirm={async (profileId, displayName) => {
          if (await workspace.renameProfile(profileId, displayName)) {
            setRenameTarget(null);
          }
        }}
      />
      <ProfileDeleteDialog
        profile={profileDeleteTarget}
        isOpen={profileDeleteTarget !== null}
        isActionLoading={isInteractionLocked}
        onOpenChange={(open) => {
          if (!open) setProfileDeleteTarget(null);
        }}
        onConfirm={async (profileId) => {
          if (await workspace.deleteProfile(profileId)) {
            setProfileDeleteTarget(null);
            onProfileDeleted?.();
          }
        }}
      />
      <ConversationDeleteDialog
        conversation={conversationDeleteTarget}
        isOpen={conversationDeleteTarget !== null}
        isActionLoading={isInteractionLocked}
        onOpenChange={(open) => {
          if (!open) setConversationDeleteTarget(null);
        }}
        onConfirm={async (conversationId) => {
          if (await workspace.deleteConversation(conversationId)) {
            setConversationDeleteTarget(null);
          }
        }}
      />
    </VStack>
  );
}

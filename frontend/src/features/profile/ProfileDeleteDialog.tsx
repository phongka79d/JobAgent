import {AlertDialog} from '@astryxdesign/core/AlertDialog';

import type {ProfileListItem} from './conversationTypes';

export type ProfileDeleteDialogProps = {
  profile: ProfileListItem | null;
  isOpen: boolean;
  isActionLoading: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (profileId: string) => Promise<void>;
};

export function ProfileDeleteDialog({
  profile,
  isOpen,
  isActionLoading,
  onOpenChange,
  onConfirm,
}: ProfileDeleteDialogProps) {
  const isPending = profile?.state === 'pending';
  const label = isPending ? 'Discard setup' : 'Delete profile and all data';
  const name = profile?.display_name ?? 'this profile';
  const cvName = profile?.cv_filename ?? 'its CV';

  return (
    <AlertDialog
      isOpen={isOpen && profile !== null}
      onOpenChange={(open) => {
        if (!isActionLoading || open) onOpenChange(open);
      }}
      title={isPending ? `Discard ${name}?` : `Delete ${name}?`}
      description={`${name} uses ${cvName}. This permanently removes the CV, profile data, evaluations, every owned conversation, and all derivative tailored-CV sessions and artifacts. This action cannot be undone.`}
      actionLabel={label}
      cancelLabel="Cancel"
      actionVariant="destructive"
      isActionLoading={isActionLoading}
      onAction={() => (profile ? onConfirm(profile.id) : undefined)}
    />
  );
}

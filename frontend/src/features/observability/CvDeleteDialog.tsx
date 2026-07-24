/**
 * Accessible profile deletion confirmation from the selected CV view.
 * Names both the profile and retained CV; workspace state owns the mutation.
 */

import {AlertDialog} from '@astryxdesign/core/AlertDialog';

export type CvDeleteDialogProps = {
  isOpen: boolean;
  /** Original filename shown in title/description. */
  fileName: string;
  profileName: string;
  isDeleting: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onConfirm: () => void;
};

/** Scope warning shared by the dialog and action tests. */
export const CV_DELETE_SCOPE_WARNING =
  'This permanently removes the profile, retained PDF, extracted document and chunks, ' +
  'owned conversations, messages, runs, tools, evaluations, and graph branch. ' +
  'Global Saved Jobs and unrelated profiles are preserved.';

export function CvDeleteDialog({
  isOpen,
  fileName,
  profileName,
  isDeleting,
  onOpenChange,
  onConfirm,
}: CvDeleteDialogProps) {
  const title = `Delete ${profileName}?`;
  const description = `Delete profile “${profileName}” and CV “${fileName}”? ${CV_DELETE_SCOPE_WARNING}`;

  return (
    <AlertDialog
      isOpen={isOpen}
      onOpenChange={(next) => {
        if (isDeleting && !next) {
          return;
        }
        onOpenChange(next);
      }}
      title={title}
      description={description}
      actionLabel="Delete profile permanently"
      cancelLabel="Cancel"
      actionVariant="destructive"
      isActionLoading={isDeleting}
      onAction={onConfirm}
      data-testid="jobagent-obs-cv-delete-dialog"
    />
  );
}

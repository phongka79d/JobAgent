/**
 * Accessible delete confirmation for a non-active CV attachment.
 * Names the target file and warns about owned-data scope (Master §10.5 / §15.2).
 */

import {AlertDialog} from '@astryxdesign/core/AlertDialog';

export type CvDeleteDialogProps = {
  isOpen: boolean;
  /** Original filename shown in title/description. */
  fileName: string;
  isDeleting: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onConfirm: () => void;
};

/** Scope warning shared by the dialog and action tests. */
export const CV_DELETE_SCOPE_WARNING =
  'This permanently removes the retained PDF, owned chunks, document snapshot, ' +
  'CV-scoped runs and tools, CV-linked chat content, and the CV-owned graph branch. ' +
  'Shared jobs, skills, and unrelated conversation history are preserved.';

export function CvDeleteDialog({
  isOpen,
  fileName,
  isDeleting,
  onOpenChange,
  onConfirm,
}: CvDeleteDialogProps) {
  const title = `Delete ${fileName}?`;
  const description = `Delete “${fileName}”? ${CV_DELETE_SCOPE_WARNING}`;

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
      actionLabel="Delete CV"
      cancelLabel="Cancel"
      actionVariant="destructive"
      isActionLoading={isDeleting}
      onAction={onConfirm}
      data-testid="jobagent-obs-cv-delete-dialog"
    />
  );
}

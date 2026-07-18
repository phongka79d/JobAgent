/**
 * Accessible delete confirmation for a saved Job (Plan 10 / Master §15.2).
 * Names the target Job title/company so the user confirms the exact row.
 */

import {AlertDialog} from '@astryxdesign/core/AlertDialog';

export type JobDeleteDialogProps = {
  isOpen: boolean;
  /** Display name used in title/description (title · company or fallback). */
  jobLabel: string;
  isDeleting: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onConfirm: () => void;
};

/** Scope warning shared by the dialog and panel tests. */
export const JOB_DELETE_SCOPE_WARNING =
  'This permanently removes the Job, its evaluations, and its Neo4j Job node and incident relationships. ' +
  'Shared Skills, seed edges, Candidate/CV data, and unrelated Jobs are preserved.';

export function JobDeleteDialog({
  isOpen,
  jobLabel,
  isDeleting,
  onOpenChange,
  onConfirm,
}: JobDeleteDialogProps) {
  const title = `Xoá JD ${jobLabel}?`;
  const description = `Xoá “${jobLabel}”? ${JOB_DELETE_SCOPE_WARNING}`;

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
      actionLabel="Xoá JD"
      cancelLabel="Huỷ"
      actionVariant="destructive"
      isActionLoading={isDeleting}
      onAction={onConfirm}
      data-testid="jobagent-saved-job-delete-dialog"
    />
  );
}

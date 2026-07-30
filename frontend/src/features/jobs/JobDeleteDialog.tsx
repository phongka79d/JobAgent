/**
 * Accessible delete confirmation for a saved Job (Plan 10 / Master §15.2).
 * Names the target Job title/company so the user confirms the exact row.
 */

import {AlertDialog} from '@astryxdesign/core/AlertDialog';

import {JOB_COPY} from './copy';

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
  'This permanently removes the saved job and its evaluations. ' +
  'Your profile, CVs, and unrelated saved jobs are preserved.';

export function JobDeleteDialog({
  isOpen,
  jobLabel,
  isDeleting,
  onOpenChange,
  onConfirm,
}: JobDeleteDialogProps) {
  const title = JOB_COPY.deleteJobTitle(jobLabel);
  const description = `Delete “${jobLabel}”? ${JOB_DELETE_SCOPE_WARNING}`;

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
      actionLabel={JOB_COPY.deleteJob}
      cancelLabel="Cancel"
      actionVariant="destructive"
      isActionLoading={isDeleting}
      onAction={onConfirm}
      data-testid="jobagent-saved-job-delete-dialog"
    />
  );
}

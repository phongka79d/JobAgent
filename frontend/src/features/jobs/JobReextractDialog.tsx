/**
 * Accessible re-extraction confirmation for a saved Job (Plan 15).
 * Names the target Job and states approved consequences before POST reextract.
 */

import {AlertDialog} from '@astryxdesign/core/AlertDialog';

export type JobReextractDialogProps = {
  isOpen: boolean;
  /** Display name used in title/description (title · company or fallback). */
  jobLabel: string;
  isReextracting: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onConfirm: () => void;
};

/** Consequence copy shared by the dialog and panel tests. */
export const JOB_REEXTRACT_CONSEQUENCES =
  'Job identity and raw source are preserved. ' +
  'If re-extraction fails before commit, the current extraction is kept. ' +
  'On success, any existing evaluation becomes stale. ' +
  'Evaluation is not run automatically.';

export function JobReextractDialog({
  isOpen,
  jobLabel,
  isReextracting,
  onOpenChange,
  onConfirm,
}: JobReextractDialogProps) {
  const title = `Re-extract JD ${jobLabel}?`;
  const description = `Re-extract “${jobLabel}”? ${JOB_REEXTRACT_CONSEQUENCES}`;

  return (
    <AlertDialog
      isOpen={isOpen}
      onOpenChange={(next) => {
        if (isReextracting && !next) {
          return;
        }
        onOpenChange(next);
      }}
      title={title}
      description={description}
      actionLabel="Re-extract JD"
      cancelLabel="Huỷ"
      actionVariant="primary"
      isActionLoading={isReextracting}
      onAction={onConfirm}
      data-testid="jobagent-saved-job-reextract-dialog"
    />
  );
}

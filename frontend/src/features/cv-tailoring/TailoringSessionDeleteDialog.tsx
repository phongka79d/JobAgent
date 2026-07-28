import {AlertDialog} from '@astryxdesign/core/AlertDialog';

export type TailoringSessionDeleteDialogProps = {
  readonly isOpen: boolean;
  readonly sessionLabel: string;
  readonly isDeleting: boolean;
  readonly onOpenChange: (isOpen: boolean) => void;
  readonly onConfirm: () => Promise<void> | void;
};

export function TailoringSessionDeleteDialog({
  isOpen,
  sessionLabel,
  isDeleting,
  onOpenChange,
  onConfirm,
}: TailoringSessionDeleteDialogProps) {
  return (
    <AlertDialog
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      title="Delete tailored CV session?"
      description={`Session “${sessionLabel}” and its versions and downloaded files will be deleted.`}
      actionLabel="Delete session"
      cancelLabel="Cancel"
      actionVariant="destructive"
      isActionLoading={isDeleting}
      onAction={onConfirm}
    />
  );
}

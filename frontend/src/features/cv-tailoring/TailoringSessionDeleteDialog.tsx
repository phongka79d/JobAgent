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
      title="Xóa phiên CV đã chỉnh?"
      description={`Phiên “${sessionLabel}” cùng mọi version và file tải xuống phái sinh sẽ bị xóa.`}
      actionLabel="Xóa phiên"
      cancelLabel="Hủy"
      actionVariant="destructive"
      isActionLoading={isDeleting}
      onAction={onConfirm}
    />
  );
}

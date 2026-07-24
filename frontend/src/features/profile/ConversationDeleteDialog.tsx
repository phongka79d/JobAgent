import {AlertDialog} from '@astryxdesign/core/AlertDialog';

import type {ConversationSummary} from './conversationTypes';

export type ConversationDeleteDialogProps = {
  conversation: ConversationSummary | null;
  isOpen: boolean;
  isActionLoading: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (conversationId: string) => Promise<void>;
};

export function ConversationDeleteDialog({
  conversation,
  isOpen,
  isActionLoading,
  onOpenChange,
  onConfirm,
}: ConversationDeleteDialogProps) {
  const title = conversation?.title ?? 'this conversation';
  return (
    <AlertDialog
      isOpen={isOpen && conversation !== null}
      onOpenChange={(open) => {
        if (!isActionLoading || open) onOpenChange(open);
      }}
      title={`Delete ${title}?`}
      description={`${title} and its complete message history will be permanently removed. This action cannot be undone.`}
      actionLabel="Delete permanently"
      cancelLabel="Cancel"
      actionVariant="destructive"
      isActionLoading={isActionLoading}
      onAction={() =>
        conversation ? onConfirm(conversation.id) : undefined
      }
    />
  );
}

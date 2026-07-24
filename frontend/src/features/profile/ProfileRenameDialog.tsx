import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog';
import {HStack} from '@astryxdesign/core/HStack';
import {
  Layout,
  LayoutContent,
  LayoutFooter,
} from '@astryxdesign/core/Layout';
import {TextInput} from '@astryxdesign/core/TextInput';

import type {ProfileListItem} from './conversationTypes';

export type ProfileRenameDialogProps = {
  profile: ProfileListItem | null;
  isOpen: boolean;
  isActionLoading: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (profileId: string, displayName: string) => Promise<void>;
};

export function ProfileRenameDialog({
  profile,
  isOpen,
  isActionLoading,
  onOpenChange,
  onConfirm,
}: ProfileRenameDialogProps) {
  const [displayName, setDisplayName] = useState('');

  useEffect(() => {
    if (isOpen) setDisplayName(profile?.display_name ?? '');
  }, [isOpen, profile]);

  const normalized = displayName.trim();
  const handleOpenChange = (open: boolean) => {
    if (!isActionLoading || open) onOpenChange(open);
  };
  return (
    <Dialog
      isOpen={isOpen && profile !== null}
      onOpenChange={handleOpenChange}
      purpose="form"
      width={400}
    >
      <Layout
        height="auto"
        header={
          <DialogHeader title="Rename profile" onOpenChange={handleOpenChange} />
        }
        content={
          <LayoutContent label="Profile name">
            <TextInput
              label="Profile name"
              value={displayName}
              onChange={setDisplayName}
              isRequired
              hasAutoFocus
              isDisabled={isActionLoading}
            />
          </LayoutContent>
        }
        footer={
          <LayoutFooter hasDivider>
            <HStack gap={2} hAlign="end">
              <Button
                label="Cancel"
                variant="secondary"
                isDisabled={isActionLoading}
                onClick={() => onOpenChange(false)}
              />
              <Button
                label="Save name"
                variant="primary"
                isLoading={isActionLoading}
                isDisabled={!profile || normalized.length === 0}
                clickAction={() =>
                  profile ? onConfirm(profile.id, normalized) : undefined
                }
              />
            </HStack>
          </LayoutFooter>
        }
      />
    </Dialog>
  );
}

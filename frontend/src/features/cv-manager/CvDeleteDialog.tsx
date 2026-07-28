import {AlertDialog} from '@astryxdesign/core/AlertDialog';

import {CV_MANAGER_COPY} from './copy';
import type {CvManagerItem} from './types';

export function CvDeleteDialog({item, isOpen, isLoading, onOpenChange, onConfirm}: {item: CvManagerItem | null; isOpen: boolean; isLoading: boolean; onOpenChange: (open: boolean) => void; onConfirm: (id: string) => Promise<boolean>}) {
  return <AlertDialog isOpen={isOpen && item !== null} onOpenChange={onOpenChange} title={CV_MANAGER_COPY.deleteTitle} description={CV_MANAGER_COPY.deleteDescription(item?.original_name ?? 'this CV')} actionLabel={CV_MANAGER_COPY.delete} cancelLabel={CV_MANAGER_COPY.cancel} actionVariant="destructive" isActionLoading={isLoading} onAction={() => item ? onConfirm(item.id) : undefined} />;
}

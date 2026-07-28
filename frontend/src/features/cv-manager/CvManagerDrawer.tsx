import {useMediaQuery} from '@astryxdesign/core';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog';
import {HStack} from '@astryxdesign/core/HStack';
import {Layout, LayoutContent, LayoutFooter} from '@astryxdesign/core/Layout';
import {List, ListItem} from '@astryxdesign/core/List';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {cvFileUrl} from './api';
import {CV_MANAGER_COPY} from './copy';
import {CvDeleteDialog} from './CvDeleteDialog';
import {ProfileReextractReview} from './ProfileReextractReview';
import type {CvManagerController, CvManagerViewState} from './state';
import type {CvManagerItem} from './types';
import './cv-manager.css';

type DrawerController = Pick<CvManagerController, 'refresh' | 'select' | 'openDeleteDialog' | 'closeDeleteDialog' | 'confirmDelete' | 'startReextract' | 'approveReview' | 'discardReview' | 'closeReview'> & {close?: CvManagerController['close']; state: CvManagerViewState};

export type CvManagerDrawerProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  controller: DrawerController;
  onActivateProfile?: (attachmentId: string) => void;
  onRetryUpload?: (attachmentId: string) => void;
  onDeleted?: () => void;
  onProfileApproved?: () => void;
};

function statusVariant(state: CvManagerItem['state']): 'success' | 'neutral' | 'warning' | 'error' {
  if (state === 'active') return 'success';
  if (state === 'failed') return 'error';
  if (state === 'staged' || state === 'deleting') return 'warning';
  return 'neutral';
}

function CvActions({item, controller, onActivateProfile, onRetryUpload}: Pick<CvManagerDrawerProps, 'controller' | 'onActivateProfile' | 'onRetryUpload'> & {item: CvManagerItem}) {
  const actions = item.allowed_actions;
  return <HStack gap={1} wrap="wrap" className="jobagent-cv-manager-actions">
    {actions.includes('preview') ? <Button label={CV_MANAGER_COPY.preview} size="sm" variant="secondary" onClick={() => window.open(cvFileUrl(item.id, 'inline'), '_blank', 'noopener,noreferrer')} /> : null}
    {actions.includes('download') ? <Button label={CV_MANAGER_COPY.download} size="sm" variant="secondary" onClick={() => window.open(cvFileUrl(item.id, 'attachment'), '_blank', 'noopener,noreferrer')} /> : null}
    {actions.includes('reextract') && item.profile_id ? <Button label={CV_MANAGER_COPY.reextract} size="sm" variant="secondary" onClick={() => { const profileId = item.profile_id; if (profileId) void controller.startReextract(profileId); }} /> : null}
    {actions.includes('activate_profile') ? <Button label={CV_MANAGER_COPY.activateProfile} size="sm" variant="secondary" onClick={() => onActivateProfile?.(item.id)} /> : null}
    {actions.includes('retry_upload') && onRetryUpload ? <Button label={CV_MANAGER_COPY.retryUpload} size="sm" variant="secondary" onClick={() => onRetryUpload(item.id)} /> : null}
    {actions.includes('delete_cv') ? <Button label={CV_MANAGER_COPY.delete} size="sm" variant="destructive" isLoading={Boolean(controller.state.pendingByAttachment[item.id])} onClick={() => controller.openDeleteDialog(item.id)} /> : null}
  </HStack>;
}

export function CvManagerDrawer({isOpen, onOpenChange, controller, onActivateProfile, onRetryUpload, onDeleted, onProfileApproved}: CvManagerDrawerProps) {
  const isNarrow = useMediaQuery('(max-width: 48rem)');
  const {state} = controller;
  const deleteItem = state.deleteTargetId === null ? null : state.items.find((item) => item.id === state.deleteTargetId) ?? null;
  const listError = state.errorsByAttachment.__list__;

  const handleOpenChange = (open: boolean) => {
    if (!open) controller.close?.();
    onOpenChange(open);
    if (!open) {
      requestAnimationFrame(() => {
        const manageButton = Array.from(document.querySelectorAll('button')).find((button) => button.textContent?.trim() === 'Manage CVs');
        manageButton?.focus();
      });
    }
  };

  return <>
    <Dialog isOpen={isOpen} onOpenChange={handleOpenChange} purpose="info" aria-label={CV_MANAGER_COPY.title} position={isNarrow ? undefined : {top: 0, right: 0, bottom: 0}} data-position={isNarrow ? undefined : 'right'} variant={isNarrow ? 'fullscreen' : 'standard'} width="min(32rem, 100vw)" maxHeight="100vh" className="jobagent-cv-manager-dialog">
      <Layout height="auto" header={<DialogHeader title={CV_MANAGER_COPY.title} onOpenChange={handleOpenChange} />} content={<LayoutContent label={CV_MANAGER_COPY.title}>
        <VStack gap={3}>
          <ProfileReextractReview controller={controller} onApproved={() => { onProfileApproved?.(); handleOpenChange(false); }} />
          {listError ? <Banner status="error" title={listError.summary} /> : null}
          {state.phase === 'loading' && state.items.length === 0 ? <Text type="body">{CV_MANAGER_COPY.loading}</Text> : null}
          {state.phase !== 'loading' && state.items.length === 0 ? <Text type="body">{CV_MANAGER_COPY.emptyTitle}</Text> : null}
          {state.items.length > 0 ? <List density="compact" hasDividers header={<Text type="label">{CV_MANAGER_COPY.listLabel}</Text>}>
            {state.items.map((item) => <ListItem key={item.id} label={item.original_name} description={<VStack gap={1}><HStack gap={2} vAlign="center"><StatusDot variant={statusVariant(item.state)} label={item.state} /><Text type="supporting">{item.state}{item.profile_display_name ? ` · ${item.profile_display_name}` : ''}</Text></HStack><CvActions item={item} controller={controller} onActivateProfile={onActivateProfile} onRetryUpload={onRetryUpload} /></VStack>} isSelected={state.selectedId === item.id} />)}
          </List> : null}
        </VStack>
      </LayoutContent>} footer={<LayoutFooter hasDivider><HStack hAlign="end"><Button label={CV_MANAGER_COPY.refresh} variant="secondary" onClick={() => void controller.refresh()} /></HStack></LayoutFooter>} />
    </Dialog>
    <CvDeleteDialog item={deleteItem} isOpen={deleteItem !== null} isLoading={deleteItem ? Boolean(state.pendingByAttachment[deleteItem.id]) : false} onOpenChange={(open) => { if (!open) controller.closeDeleteDialog(); }} onConfirm={async (id) => { const deleted = await controller.confirmDelete(id); if (deleted) onDeleted?.(); return deleted; }} />
  </>;
}

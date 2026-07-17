/**
 * CV Manager inspector panel — list attachments; open/download; re-extract /
 * make active through approval; confirm non-active deletion.
 */

import {useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {VStack} from '@astryxdesign/core/VStack';

import {CvDeleteDialog} from './CvDeleteDialog';
import type {CvManagerActionKind} from './cvManagerTypes';
import {ObservabilityListSkeleton} from './ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from './ObservabilityPanelHeader';
import {formatObservabilityDateTime} from './observabilityFormat';
import type {CachedResource} from './state';
import type {
  CvHistoryItem,
  CvHistoryPage,
  ObservabilitySafeError,
} from './types';

export type CvManagerPanelProps = {
  resource: CachedResource<CvHistoryPage>;
  selectedAttachmentId: string | null;
  pendingByAttachment: Readonly<Record<string, CvManagerActionKind>>;
  errorsByAttachment: Readonly<Record<string, ObservabilitySafeError>>;
  onSelect: (item: CvHistoryItem) => void;
  onOpenFile: (item: CvHistoryItem) => void;
  onRefresh: () => void;
  /** Re-extract (active) or Make active (archived/non-active) → SSE path. */
  onReprocess: (item: CvHistoryItem) => void;
  /** Confirmed non-active delete → confirmDelete + focused invalidation. */
  onConfirmDelete: (item: CvHistoryItem) => Promise<'success' | 'duplicate' | 'error'>;
  onClearError: (attachmentId: string) => void;
};

function attachmentVariant(state: CvHistoryItem['state']) {
  if (state === 'active') return 'success' as const;
  if (state === 'staged') return 'warning' as const;
  if (state === 'failed') return 'error' as const;
  return 'neutral' as const;
}

/** Delete is never offered for the active attachment (Master §10.5 / §15.2). */
export function canDeleteCv(item: CvHistoryItem): boolean {
  return item.state !== 'active';
}

function rowEndContent(item: CvHistoryItem) {
  if (item.state === 'active') {
    return (
      <Badge
        variant="success"
        label="Active"
        data-testid={`jobagent-obs-cv-active-badge-${item.id}`}
      />
    );
  }
  return item.file_available ? 'Available' : 'Unavailable';
}

export function CvManagerPanel({
  resource,
  selectedAttachmentId,
  pendingByAttachment,
  errorsByAttachment,
  onSelect,
  onOpenFile,
  onRefresh,
  onReprocess,
  onConfirmDelete,
  onClearError,
}: CvManagerPanelProps) {
  const items = resource.data?.items ?? [];
  const selectedItem =
    items.find((item) => item.id === selectedAttachmentId) ?? null;
  const [deleteTarget, setDeleteTarget] = useState<CvHistoryItem | null>(null);

  const selectedPending = selectedItem
    ? pendingByAttachment[selectedItem.id]
    : undefined;
  const selectedError = selectedItem
    ? errorsByAttachment[selectedItem.id]
    : undefined;
  const isSelectedPending = selectedPending !== undefined;
  const isDeletePending = selectedPending === 'delete';
  const isReprocessPending = selectedPending === 'reprocess';

  return (
    <VStack
      gap={2}
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-cv-history"
      role="tabpanel"
      id="jobagent-obs-panel-cv-history"
      aria-labelledby="jobagent-obs-tab-cv-history"
    >
      <ObservabilityPanelHeader
        eyebrow="Attachments"
        title="CV Manager"
        onRefresh={onRefresh}
        isRefreshing={resource.phase === 'loading'}
        refreshTestId="jobagent-obs-cv-history-refresh"
      />

      {resource.phase === 'loading' && !resource.data ? (
        <ObservabilityListSkeleton
          rows={3}
          testId="jobagent-obs-cv-history-loading"
        />
      ) : null}

      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title="CV Manager unavailable"
          description={`${resource.error.summary} (${resource.error.code})`}
          container="section"
          data-testid="jobagent-obs-cv-history-error"
        />
      ) : null}

      {resource.phase === 'empty' ||
      (resource.loaded && items.length === 0 && resource.phase !== 'error') ? (
        <EmptyState
          title="No CV uploads yet"
          description="Upload a CV from Overview to start CV Manager."
          isCompact
          data-testid="jobagent-obs-cv-history-empty"
        />
      ) : null}

      {items.length > 0 ? (
        <List density="compact" hasDividers header="CV Manager">
          {items.map((item) => (
            <ListItem
              key={item.id}
              label={item.original_name}
              description={`${item.state} · ${formatObservabilityDateTime(item.created_at)}`}
              startContent={
                <StatusDot
                  variant={attachmentVariant(item.state)}
                  label={item.state}
                />
              }
              endContent={rowEndContent(item)}
              isSelected={item.id === selectedAttachmentId}
              onClick={() => onSelect(item)}
              data-testid={`jobagent-obs-cv-select-${item.id}`}
            />
          ))}
        </List>
      ) : null}

      {selectedItem ? (
        <VStack
          gap={2}
          className="jobagent-obs-detail"
          data-testid="jobagent-obs-cv-detail"
        >
          <MetadataList
            columns="single"
            label={{position: 'top'}}
            title="Selected CV"
          >
            <MetadataListItem label="State">
              {selectedItem.state === 'active' ? (
                <Badge
                  variant="success"
                  label="Active"
                  data-testid={`jobagent-obs-cv-detail-active-badge-${selectedItem.id}`}
                />
              ) : (
                selectedItem.state
              )}
            </MetadataListItem>
            <MetadataListItem label="Hash">
              {selectedItem.file_hash_abbreviated}
            </MetadataListItem>
            <MetadataListItem label="Page count">
              {selectedItem.page_count ?? 'Unavailable'}
            </MetadataListItem>
            <MetadataListItem label="Size">
              {selectedItem.size_bytes} bytes
            </MetadataListItem>
            <MetadataListItem label="Created">
              {formatObservabilityDateTime(selectedItem.created_at)}
            </MetadataListItem>
            <MetadataListItem label="Updated">
              {formatObservabilityDateTime(selectedItem.updated_at)}
            </MetadataListItem>
          </MetadataList>

          {selectedError ? (
            <Banner
              status="error"
              title="Action failed"
              description={`${selectedError.summary} (${selectedError.code})`}
              container="section"
              data-testid={`jobagent-obs-cv-action-error-${selectedItem.id}`}
            />
          ) : null}

          <HStack
            gap={1}
            wrap="wrap"
            vAlign="center"
            className="jobagent-obs-cv-actions"
            data-testid={`jobagent-obs-cv-actions-${selectedItem.id}`}
          >
            <Button
              label="Open / download"
              variant="secondary"
              size="sm"
              isDisabled={!selectedItem.file_available || isSelectedPending}
              onClick={() => onOpenFile(selectedItem)}
              data-testid={`jobagent-obs-cv-open-${selectedItem.id}`}
            />

            {selectedItem.state === 'active' ? (
              <Button
                label="Re-extract"
                variant="secondary"
                size="sm"
                isDisabled={isSelectedPending || !selectedItem.file_available}
                isLoading={isReprocessPending}
                onClick={() => onReprocess(selectedItem)}
                data-testid={`jobagent-obs-cv-reextract-${selectedItem.id}`}
              />
            ) : (
              <Button
                label="Make active"
                variant="secondary"
                size="sm"
                isDisabled={isSelectedPending || !selectedItem.file_available}
                isLoading={isReprocessPending}
                onClick={() => onReprocess(selectedItem)}
                data-testid={`jobagent-obs-cv-make-active-${selectedItem.id}`}
              />
            )}

            {canDeleteCv(selectedItem) ? (
              <Button
                label="Delete"
                variant="destructive"
                size="sm"
                isDisabled={isSelectedPending}
                isLoading={isDeletePending}
                onClick={() => setDeleteTarget(selectedItem)}
                data-testid={`jobagent-obs-cv-delete-${selectedItem.id}`}
              />
            ) : null}

            {selectedError ? (
              <Button
                label="Dismiss error"
                variant="ghost"
                size="sm"
                isDisabled={isSelectedPending}
                onClick={() => onClearError(selectedItem.id)}
                data-testid={`jobagent-obs-cv-clear-error-${selectedItem.id}`}
              />
            ) : null}
          </HStack>
        </VStack>
      ) : null}

      <CvDeleteDialog
        isOpen={deleteTarget !== null}
        fileName={deleteTarget?.original_name ?? ''}
        isDeleting={
          deleteTarget !== null &&
          pendingByAttachment[deleteTarget.id] === 'delete'
        }
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
        onConfirm={() => {
          if (!deleteTarget) {
            return;
          }
          const target = deleteTarget;
          void onConfirmDelete(target).then((outcome) => {
            if (outcome === 'success' || outcome === 'duplicate') {
              setDeleteTarget(null);
            }
            // Partial failure keeps dialog closable; error banner remains on row.
            if (outcome === 'error') {
              setDeleteTarget(null);
            }
          });
        }}
      />
    </VStack>
  );
}

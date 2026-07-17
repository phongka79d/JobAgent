/**
 * CV history inspector panel - select attachment; open/download when file_available.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {List, ListItem} from '@astryxdesign/core/List';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {VStack} from '@astryxdesign/core/VStack';

import {ObservabilityListSkeleton} from './ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from './ObservabilityPanelHeader';
import {formatObservabilityDateTime} from './observabilityFormat';
import type {CachedResource} from './state';
import type {CvHistoryItem, CvHistoryPage} from './types';

export type CvHistoryPanelProps = {
  resource: CachedResource<CvHistoryPage>;
  selectedAttachmentId: string | null;
  onSelect: (item: CvHistoryItem) => void;
  onOpenFile: (item: CvHistoryItem) => void;
  onRefresh: () => void;
};

function attachmentVariant(state: CvHistoryItem['state']) {
  if (state === 'active') return 'success' as const;
  if (state === 'staged') return 'warning' as const;
  if (state === 'failed') return 'error' as const;
  return 'neutral' as const;
}

export function CvHistoryPanel({
  resource,
  selectedAttachmentId,
  onSelect,
  onOpenFile,
  onRefresh,
}: CvHistoryPanelProps) {
  const items = resource.data?.items ?? [];
  const selectedItem =
    items.find((item) => item.id === selectedAttachmentId) ?? null;

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
        title="CV history"
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
          title="CV history unavailable"
          description={`${resource.error.summary} (${resource.error.code})`}
          container="section"
          data-testid="jobagent-obs-cv-history-error"
        />
      ) : null}

      {resource.phase === 'empty' ||
      (resource.loaded && items.length === 0 && resource.phase !== 'error') ? (
        <EmptyState
          title="No CV uploads yet"
          description="Upload a CV from Overview to start history."
          isCompact
          data-testid="jobagent-obs-cv-history-empty"
        />
      ) : null}

      {items.length > 0 ? (
        <List density="compact" hasDividers header="CV history">
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
              endContent={item.file_available ? 'Available' : 'Unavailable'}
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
              {selectedItem.state}
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
          <Button
            label="Open / download"
            variant="secondary"
            size="sm"
            isDisabled={!selectedItem.file_available}
            onClick={() => onOpenFile(selectedItem)}
            data-testid={`jobagent-obs-cv-open-${selectedItem.id}`}
          />
        </VStack>
      ) : null}
    </VStack>
  );
}

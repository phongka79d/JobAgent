/**
 * CV history inspector panel — select attachment; open/download when file_available.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Spinner} from '@astryxdesign/core/Spinner';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import type {CachedResource} from './state';
import type {CvHistoryItem, CvHistoryPage} from './types';

export type CvHistoryPanelProps = {
  resource: CachedResource<CvHistoryPage>;
  selectedAttachmentId: string | null;
  onSelect: (item: CvHistoryItem) => void;
  onOpenFile: (item: CvHistoryItem) => void;
  onRefresh: () => void;
};

export function CvHistoryPanel({
  resource,
  selectedAttachmentId,
  onSelect,
  onOpenFile,
  onRefresh,
}: CvHistoryPanelProps) {
  const items = resource.data?.items ?? [];

  return (
    <div
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-cv-history"
      role="tabpanel"
      id="jobagent-obs-panel-cv-history"
      aria-labelledby="jobagent-obs-tab-cv-history"
    >
      <HStack gap={2} hAlign="between" vAlign="center">
        <Text type="label">CV history</Text>
        <Button
          label="Refresh"
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          data-testid="jobagent-obs-cv-history-refresh"
        />
      </HStack>

      {resource.phase === 'loading' && !resource.data ? (
        <HStack gap={2} vAlign="center" data-testid="jobagent-obs-cv-history-loading">
          <Spinner size="sm" />
          <Text type="body" color="secondary">
            Loading CV history…
          </Text>
        </HStack>
      ) : null}

      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title="CV history unavailable"
          description={`${resource.error.summary} (${resource.error.code})`}
          container="card"
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
        <VStack gap={2} width="100%">
          {items.map((item) => {
            const selected = item.id === selectedAttachmentId;
            return (
              <div
                key={item.id}
                className="jobagent-obs-row"
                data-testid={`jobagent-obs-cv-item-${item.id}`}
                data-selected={selected ? 'true' : 'false'}
              >
                <Text type="body" className="jobagent-obs-meta">
                  {item.original_name}
                </Text>
                <Text type="supporting" color="secondary" className="jobagent-obs-meta">
                  {item.state}
                  {' · '}
                  {item.file_hash_abbreviated}
                  {item.file_available ? '' : ' · file unavailable'}
                </Text>
                <div className="jobagent-obs-row-actions">
                  <Button
                    label={selected ? 'Selected' : 'Select for chunks'}
                    variant={selected ? 'primary' : 'secondary'}
                    size="sm"
                    onClick={() => onSelect(item)}
                    data-testid={`jobagent-obs-cv-select-${item.id}`}
                  />
                  <Button
                    label="Open / download"
                    variant="secondary"
                    size="sm"
                    isDisabled={!item.file_available}
                    onClick={() => onOpenFile(item)}
                    data-testid={`jobagent-obs-cv-open-${item.id}`}
                  />
                </div>
              </div>
            );
          })}
        </VStack>
      ) : null}

      {resource.phase === 'loading' && resource.data ? (
        <Text type="supporting" color="secondary">
          Refreshing…
        </Text>
      ) : null}
    </div>
  );
}

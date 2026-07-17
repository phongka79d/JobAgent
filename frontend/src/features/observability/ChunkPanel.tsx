/**
 * LLM chunk inspector - preview list; full text only after explicit expand.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {List, ListItem} from '@astryxdesign/core/List';
import {Spinner} from '@astryxdesign/core/Spinner';
import {VStack} from '@astryxdesign/core/VStack';

import {ObservabilityListSkeleton} from './ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from './ObservabilityPanelHeader';
import type {CachedResource} from './state';
import {chunkDetailKey} from './state';
import type {ChunkDetail, ChunkListPage} from './types';

export type ChunkPanelProps = {
  selectedAttachmentId: string | null;
  listResource: CachedResource<ChunkListPage> | null;
  details: Record<string, CachedResource<ChunkDetail>>;
  expandedOrdinal: number | null;
  onExpand: (ordinal: number) => void;
  onCollapse: () => void;
  onRefresh: () => void;
};

export function ChunkPanel({
  selectedAttachmentId,
  listResource,
  details,
  expandedOrdinal,
  onExpand,
  onCollapse,
  onRefresh,
}: ChunkPanelProps) {
  if (!selectedAttachmentId) {
    return (
      <VStack
        gap={2}
        className="jobagent-obs-panel"
        data-testid="jobagent-obs-chunks"
        role="tabpanel"
        id="jobagent-obs-panel-chunks"
        aria-labelledby="jobagent-obs-tab-chunks"
      >
        <EmptyState
          title="No CV selected"
          description="Select a CV from CV history to inspect LLM chunks."
          isCompact
          data-testid="jobagent-obs-chunks-no-selection"
        />
      </VStack>
    );
  }

  const items = listResource?.data?.items ?? [];
  const phase = listResource?.phase ?? 'idle';
  const detail =
    expandedOrdinal === null
      ? null
      : details[chunkDetailKey(selectedAttachmentId, expandedOrdinal)];

  return (
    <VStack
      gap={2}
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-chunks"
      role="tabpanel"
      id="jobagent-obs-panel-chunks"
      aria-labelledby="jobagent-obs-tab-chunks"
    >
      <ObservabilityPanelHeader
        eyebrow="Extracted text"
        title="LLM chunks"
        onRefresh={onRefresh}
        isRefreshing={phase === 'loading'}
        refreshTestId="jobagent-obs-chunks-refresh"
      />

      {phase === 'loading' && !listResource?.data ? (
        <ObservabilityListSkeleton
          rows={3}
          testId="jobagent-obs-chunks-loading"
        />
      ) : null}

      {phase === 'error' && listResource?.error ? (
        <Banner
          status="error"
          title="Chunks unavailable"
          description={`${listResource.error.summary} (${listResource.error.code})`}
          container="section"
          data-testid="jobagent-obs-chunks-error"
        />
      ) : null}

      {phase === 'empty' ||
      (listResource?.loaded && items.length === 0 && phase !== 'error') ? (
        <EmptyState
          title="No chunks for this CV"
          description="Historical uploads without extracted text show an unavailable state."
          isCompact
          data-testid="jobagent-obs-chunks-empty"
        />
      ) : null}

      {items.length > 0 ? (
        <List density="compact" hasDividers header="LLM chunks">
          {items.map((item) => {
            const key = chunkDetailKey(item.attachment_id, item.ordinal);
            return (
              <ListItem
                key={key}
                label={`Chunk #${item.ordinal}`}
                description={item.preview}
                endContent={`${item.char_count} chars · ~${item.token_estimate} tokens`}
                isSelected={expandedOrdinal === item.ordinal}
                onClick={() =>
                  expandedOrdinal === item.ordinal
                    ? onCollapse()
                    : onExpand(item.ordinal)
                }
                data-testid={`jobagent-obs-chunk-toggle-${item.ordinal}`}
              />
            );
          })}
        </List>
      ) : null}

      {expandedOrdinal !== null ? (
        <VStack gap={2} className="jobagent-obs-detail">
          {detail?.phase === 'loading' && !detail.data ? (
            <Spinner size="sm" label="Loading full text..." />
          ) : null}
          {detail?.phase === 'error' && detail.error ? (
            <Banner
              status="error"
              title="Full text unavailable"
              description={`${detail.error.summary} (${detail.error.code})`}
              container="section"
              data-testid={`jobagent-obs-chunk-detail-error-${expandedOrdinal}`}
            />
          ) : null}
          {detail?.data ? (
            <pre
              className="jobagent-obs-fulltext"
              data-testid={`jobagent-obs-chunk-fulltext-${expandedOrdinal}`}
            >
              {detail.data.text}
            </pre>
          ) : null}
        </VStack>
      ) : null}
    </VStack>
  );
}

/**
 * LLM chunk inspector — preview list; full text only after explicit expand.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Spinner} from '@astryxdesign/core/Spinner';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

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
      <div
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
      </div>
    );
  }

  const items = listResource?.data?.items ?? [];
  const phase = listResource?.phase ?? 'idle';

  return (
    <div
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-chunks"
      role="tabpanel"
      id="jobagent-obs-panel-chunks"
      aria-labelledby="jobagent-obs-tab-chunks"
    >
      <HStack gap={2} hAlign="between" vAlign="center">
        <Text type="label">LLM chunks</Text>
        <Button
          label="Refresh"
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          data-testid="jobagent-obs-chunks-refresh"
        />
      </HStack>

      {phase === 'loading' && !listResource?.data ? (
        <HStack gap={2} vAlign="center" data-testid="jobagent-obs-chunks-loading">
          <Spinner size="sm" />
          <Text type="body" color="secondary">
            Loading chunks…
          </Text>
        </HStack>
      ) : null}

      {phase === 'error' && listResource?.error ? (
        <Banner
          status="error"
          title="Chunks unavailable"
          description={`${listResource.error.summary} (${listResource.error.code})`}
          container="card"
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
        <VStack gap={2} width="100%">
          {items.map((item) => {
            const key = chunkDetailKey(item.attachment_id, item.ordinal);
            const detail = details[key];
            const isExpanded = expandedOrdinal === item.ordinal;
            return (
              <div
                key={key}
                className="jobagent-obs-row"
                data-testid={`jobagent-obs-chunk-${item.ordinal}`}
              >
                <Text type="body" className="jobagent-obs-meta">
                  Chunk #{item.ordinal}
                </Text>
                <Text type="supporting" color="secondary" className="jobagent-obs-meta">
                  {item.char_count} chars · ~{item.token_estimate} tokens
                </Text>
                <Text type="body" className="jobagent-obs-meta">
                  {item.preview}
                </Text>
                <div className="jobagent-obs-row-actions">
                  {isExpanded ? (
                    <Button
                      label="Hide full text"
                      variant="secondary"
                      size="sm"
                      onClick={onCollapse}
                      data-testid={`jobagent-obs-chunk-collapse-${item.ordinal}`}
                    />
                  ) : (
                    <Button
                      label="Expand full text"
                      variant="secondary"
                      size="sm"
                      onClick={() => onExpand(item.ordinal)}
                      data-testid={`jobagent-obs-chunk-expand-${item.ordinal}`}
                    />
                  )}
                </div>
                {isExpanded && detail?.phase === 'loading' && !detail.data ? (
                  <HStack gap={2} vAlign="center">
                    <Spinner size="sm" />
                    <Text type="supporting">Loading full text…</Text>
                  </HStack>
                ) : null}
                {isExpanded && detail?.phase === 'error' && detail.error ? (
                  <Banner
                    status="error"
                    title="Full text unavailable"
                    description={`${detail.error.summary} (${detail.error.code})`}
                    container="card"
                    data-testid={`jobagent-obs-chunk-detail-error-${item.ordinal}`}
                  />
                ) : null}
                {isExpanded && detail?.data ? (
                  <pre
                    className="jobagent-obs-fulltext"
                    data-testid={`jobagent-obs-chunk-fulltext-${item.ordinal}`}
                  >
                    {detail.data.text}
                  </pre>
                ) : null}
              </div>
            );
          })}
        </VStack>
      ) : null}
    </div>
  );
}

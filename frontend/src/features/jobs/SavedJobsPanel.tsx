/**
 * Compact saved-JD list + selected detail + actions (Plan 10 / Master §15.2).
 * Composes accepted savedJobsState; reuses MatchCard via SavedJobDetail.
 */

import {useEffect, useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {ObservabilityListSkeleton} from '../observability/ObservabilityListSkeleton';
import {ObservabilityPanelHeader} from '../observability/ObservabilityPanelHeader';
import {formatDisplayScore} from './matchResult';
import {JobDeleteDialog} from './JobDeleteDialog';
import {
  formatSavedJobLabel,
  SavedJobDetailView,
} from './SavedJobDetail';
import type {
  CachedResource,
  SavedJobActionKind,
  SavedJobsActionSlice,
} from './savedJobsState';
import type {
  JobJdQuality,
  JobProcessingStatus,
  SavedJobDetail,
  SavedJobListItem,
  SavedJobListPage,
  SavedJobsSafeError,
} from './types';

export type SavedJobsPanelProps = {
  list: CachedResource<SavedJobListPage>;
  details: Readonly<Record<string, CachedResource<SavedJobDetail>>>;
  selectedJobId: string | null;
  actions: SavedJobsActionSlice;
  onSelect: (jobId: string) => void;
  /** Initial/cached list load when the panel becomes active (not force). */
  onLoad: () => void;
  onRefresh: () => void;
  onEvaluate: (jobId: string) => Promise<'success' | 'duplicate' | 'error'>;
  onConfirmDelete: (
    jobId: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
  onClearError: (jobId: string) => void;
  onRefreshDetail: (jobId: string) => void;
};

function processingVariant(
  status: JobProcessingStatus,
): 'success' | 'error' | 'accent' | 'neutral' | 'warning' {
  switch (status) {
    case 'processed':
      return 'success';
    case 'failed':
      return 'error';
    case 'processing':
      return 'accent';
    case 'received':
    default:
      return 'neutral';
  }
}

function qualityLabel(quality: JobJdQuality | null): string | null {
  return quality;
}

function evaluationEndContent(item: SavedJobListItem) {
  if (item.evaluation_state === 'stale') {
    return (
      <Badge
        variant="warning"
        label="Cần đánh giá lại"
        data-testid={`jobagent-saved-job-stale-badge-${item.id}`}
      />
    );
  }
  if (item.latest_score !== null && item.evaluation_state === 'current') {
    return (
      <Text
        type="supporting"
        as="span"
        data-testid={`jobagent-saved-job-score-${item.id}`}
      >
        {formatDisplayScore(item.latest_score)}
      </Text>
    );
  }
  if (item.evaluation_state === 'none') {
    return (
      <Text
        type="supporting"
        color="secondary"
        as="span"
        data-testid={`jobagent-saved-job-eval-none-${item.id}`}
      >
        Chưa đánh giá
      </Text>
    );
  }
  if (item.latest_score !== null) {
    return (
      <Text
        type="supporting"
        as="span"
        data-testid={`jobagent-saved-job-score-${item.id}`}
      >
        {formatDisplayScore(item.latest_score)}
      </Text>
    );
  }
  return null;
}

function rowDescription(item: SavedJobListItem): string {
  const company = item.company?.trim() || 'Unknown company';
  const quality = qualityLabel(item.jd_quality);
  const parts = [company, item.processing_status];
  if (quality) {
    parts.push(quality);
  }
  parts.push(item.evaluation_state);
  return parts.join(' · ');
}

export function SavedJobsPanel({
  list,
  details,
  selectedJobId,
  actions,
  onSelect,
  onLoad,
  onRefresh,
  onEvaluate,
  onConfirmDelete,
  onClearError,
  onRefreshDetail,
}: SavedJobsPanelProps) {
  const items = list.data?.items ?? [];
  const selectedItem =
    items.find((item) => item.id === selectedJobId) ?? null;
  const selectedDetail =
    selectedJobId !== null ? (details[selectedJobId] ?? null) : null;
  const [deleteTarget, setDeleteTarget] = useState<SavedJobListItem | null>(
    null,
  );

  // Load once when the tab panel mounts; state owner skips when already cached.
  // Mount-only on purpose: remount on tab re-entry; parent callback identity may churn.
  useEffect(() => {
    onLoad();
  }, []);

  const selectedPending: SavedJobActionKind | undefined = selectedItem
    ? actions.pendingByJob[selectedItem.id]
    : undefined;
  const selectedError: SavedJobsSafeError | undefined = selectedItem
    ? actions.errorsByJob[selectedItem.id]
    : undefined;

  return (
    <VStack
      gap={2}
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-saved-jobs"
      role="tabpanel"
      id="jobagent-obs-panel-saved-jobs"
      aria-labelledby="jobagent-obs-tab-saved-jobs"
    >
      <ObservabilityPanelHeader
        eyebrow="Saved jobs"
        title="JD đã lưu"
        onRefresh={onRefresh}
        isRefreshing={list.phase === 'loading'}
        refreshTestId="jobagent-obs-saved-jobs-refresh"
      />

      {list.phase === 'loading' && !list.data ? (
        <ObservabilityListSkeleton
          rows={3}
          testId="jobagent-obs-saved-jobs-loading"
        />
      ) : null}

      {list.phase === 'error' && list.error ? (
        <Banner
          status="error"
          title="Saved JDs unavailable"
          description={`${list.error.summary} (${list.error.code})`}
          container="section"
          data-testid="jobagent-obs-saved-jobs-error"
        />
      ) : null}

      {list.phase === 'empty' ||
      (list.loaded && items.length === 0 && list.phase !== 'error') ? (
        <EmptyState
          title="Chưa có JD đã lưu"
          description="Save a job description from chat or match results to evaluate it here."
          isCompact
          data-testid="jobagent-obs-saved-jobs-empty"
        />
      ) : null}

      {items.length > 0 ? (
        <List
          density="compact"
          hasDividers
          header="JD đã lưu"
          data-testid="jobagent-obs-saved-jobs-list"
        >
          {items.map((item) => {
            const label = formatSavedJobLabel(item);
            const pending = actions.pendingByJob[item.id];
            return (
              <ListItem
                key={item.id}
                label={label}
                description={rowDescription(item)}
                startContent={
                  <StatusDot
                    variant={processingVariant(item.processing_status)}
                    label={item.processing_status}
                  />
                }
                endContent={
                  <HStack gap={1} vAlign="center">
                    {pending ? (
                      <Text type="supporting" color="secondary" as="span">
                        {pending === 'evaluate' ? 'Evaluating…' : 'Deleting…'}
                      </Text>
                    ) : null}
                    {evaluationEndContent(item)}
                  </HStack>
                }
                isSelected={item.id === selectedJobId}
                isDisabled={pending === 'delete'}
                onClick={() => onSelect(item.id)}
                data-testid={`jobagent-saved-job-select-${item.id}`}
                data-evaluation-state={item.evaluation_state}
                data-job-id={item.id}
                data-full-label={label}
              />
            );
          })}
        </List>
      ) : null}

      {selectedItem ? (
        <SavedJobDetailView
          job={selectedItem}
          detail={selectedDetail}
          pendingKind={selectedPending}
          actionError={selectedError}
          onEvaluate={(jobId) => {
            void onEvaluate(jobId);
          }}
          onRequestDelete={(job) => setDeleteTarget(job)}
          onClearError={onClearError}
          onRefreshDetail={onRefreshDetail}
        />
      ) : null}

      <JobDeleteDialog
        isOpen={deleteTarget !== null}
        jobLabel={
          deleteTarget ? formatSavedJobLabel(deleteTarget) : ''
        }
        isDeleting={
          deleteTarget !== null &&
          actions.pendingByJob[deleteTarget.id] === 'delete'
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
          void onConfirmDelete(target.id).then((outcome) => {
            if (
              outcome === 'success' ||
              outcome === 'duplicate' ||
              outcome === 'error'
            ) {
              setDeleteTarget(null);
            }
          });
        }}
      />
    </VStack>
  );
}

// Re-export helpers for tests / callers that only need the action matrix.
export {evaluateActionLabel, formatSavedJobLabel} from './SavedJobDetail';

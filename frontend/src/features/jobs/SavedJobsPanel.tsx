/**
 * Compact saved-JD list + selected detail + actions (Plan 10 / Master §15.2).
 * Composes accepted savedJobsState; reuses MatchCard via SavedJobDetail.
 */

import {useEffect, useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Skeleton} from '@astryxdesign/core/Skeleton';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {formatDisplayScore} from './matchResult';
import {JOB_COPY, savedJobDisplayLabel} from './copy';
import './jobs.css';
import {JobDeleteDialog} from './JobDeleteDialog';
import {JobReextractDialog} from './JobReextractDialog';
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
  onConfirmReextract: (
    jobId: string,
  ) => Promise<'success' | 'duplicate' | 'error'>;
  onClearError: (jobId: string) => void;
  onRefreshDetail: (jobId: string) => void;
  canCreateTailoredCv?: boolean;
  isTailoringPending?: boolean;
  onCreateTailoredCv?: (jobId: string) => void;
};

function SavedJobsPanelHeader({
  title,
  onRefresh,
  isRefreshing,
  refreshTestId,
}: {
  eyebrow: string;
  title: string;
  onRefresh: () => void;
  isRefreshing: boolean;
  refreshTestId: string;
}) {
  return (
    <HStack hAlign="between" vAlign="center">
      <Heading level={2}>{title}</Heading>
      <Button
        label="Refresh"
        size="sm"
        variant="ghost"
        isLoading={isRefreshing}
        onClick={onRefresh}
        data-testid={refreshTestId}
      />
    </HStack>
  );
}

function SavedJobsListSkeleton({
  rows,
  testId,
}: {
  rows: number;
  testId: string;
}) {
  return (
    <VStack gap={2} data-testid={testId}>
      {Array.from({length: rows}, (_, index) => (
        <Skeleton key={index} height="var(--spacing-8)" index={index} />
      ))}
    </VStack>
  );
}

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
  switch (quality) {
    case 'full':
      return 'Complete';
    case 'partial':
      return 'Partial';
    case 'unscorable':
      return 'Not scorable';
    default:
      return null;
  }
}

function processingLabel(status: JobProcessingStatus): string {
  switch (status) {
    case 'processed':
      return 'Processed';
    case 'processing':
      return 'Processing';
    case 'failed':
      return 'Processing failed';
    case 'received':
    default:
      return 'Received';
  }
}

function listRowLabel(item: SavedJobListItem): string {
  return savedJobDisplayLabel(item);
}

function evaluationEndContent(item: SavedJobListItem) {
  if (item.evaluation_state === 'stale') {
    return (
      <Badge
        variant="warning"
        label="Needs re-evaluation"
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
        Not evaluated
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
  const parts = item.title?.trim() ? [company] : [];
  parts.push(processingLabel(item.processing_status));
  if (quality) {
    parts.push(quality);
  }
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
  onConfirmReextract,
  onClearError,
  onRefreshDetail,
  canCreateTailoredCv = false,
  isTailoringPending = false,
  onCreateTailoredCv,
}: SavedJobsPanelProps) {
  const items = list.data?.items ?? [];
  const selectedItem =
    items.find((item) => item.id === selectedJobId) ?? null;
  const selectedDetail =
    selectedJobId !== null ? (details[selectedJobId] ?? null) : null;
  const [deleteTarget, setDeleteTarget] = useState<SavedJobListItem | null>(
    null,
  );
  const [reextractTarget, setReextractTarget] =
    useState<SavedJobListItem | null>(null);

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
      className="jobagent-saved-jobs-workspace"
      data-testid="jobagent-saved-jobs"
    >
      <VStack
        gap={2}
        className="jobagent-saved-jobs-master-pane"
        data-testid="jobagent-saved-jobs-master-pane"
      >
        <SavedJobsPanelHeader
          eyebrow={JOB_COPY.savedJobsEyebrow}
          title="Saved jobs"
          onRefresh={onRefresh}
          isRefreshing={list.phase === 'loading'}
          refreshTestId="jobagent-obs-saved-jobs-refresh"
        />

        {list.phase === 'loading' && !list.data ? (
          <SavedJobsListSkeleton
            rows={3}
            testId="jobagent-obs-saved-jobs-loading"
          />
        ) : null}

        {list.phase === 'error' && list.error ? (
          <Banner
            status="error"
            title="Unable to load saved jobs"
            description={list.error.summary}
            container="section"
            data-testid="jobagent-obs-saved-jobs-error"
          />
        ) : null}

        {list.phase === 'empty' ||
        (list.loaded && items.length === 0 && list.phase !== 'error') ? (
          <EmptyState
            title="No saved jobs yet"
            description="Save a job description from chat to evaluate it here."
            isCompact
            data-testid="jobagent-obs-saved-jobs-empty"
          />
        ) : null}

        {items.length > 0 ? (
          <List
            density="compact"
            hasDividers
            header={`${items.length} saved jobs`}
            data-testid="jobagent-obs-saved-jobs-list"
          >
            {items.map((item) => {
              const label = listRowLabel(item);
              const pending = actions.pendingByJob[item.id];
              return (
                <ListItem
                  key={item.id}
                  label={label}
                  description={rowDescription(item)}
                  startContent={
                    <StatusDot
                      variant={processingVariant(item.processing_status)}
                      label={processingLabel(item.processing_status)}
                    />
                  }
                  endContent={
                    <HStack gap={1} vAlign="center">
                      {pending ? (
                        <Text type="supporting" color="secondary" as="span">
                          {pending === 'evaluate'
                            ? 'Evaluating…'
                            : pending === 'reextract'
                              ? 'Extracting…'
                              : 'Deleting…'}
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
                  data-full-label={formatSavedJobLabel(item)}
                />
              );
            })}
          </List>
        ) : null}
      </VStack>

      <VStack
        gap={2}
        className="jobagent-saved-jobs-detail-pane"
        data-testid="jobagent-saved-jobs-detail-pane"
      >
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
            onRequestReextract={(job) => setReextractTarget(job)}
            onClearError={onClearError}
            onRefreshDetail={onRefreshDetail}
            canCreateTailoredCv={canCreateTailoredCv}
            isTailoringPending={isTailoringPending}
            onCreateTailoredCv={onCreateTailoredCv}
          />
        ) : (
          <EmptyState
            title="Choose a saved job"
            description="Select a saved job to view its details and CV match result."
            isCompact
          />
        )}
      </VStack>

      {deleteTarget ? (
        <JobDeleteDialog
          isOpen
          jobLabel={formatSavedJobLabel(deleteTarget)}
          isDeleting={actions.pendingByJob[deleteTarget.id] === 'delete'}
          onOpenChange={(open) => {
            if (!open) {
              setDeleteTarget(null);
            }
          }}
          onConfirm={() => {
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
      ) : null}

      <JobReextractDialog
        isOpen={reextractTarget !== null}
        jobLabel={
          reextractTarget ? formatSavedJobLabel(reextractTarget) : ''
        }
        isReextracting={
          reextractTarget !== null &&
          actions.pendingByJob[reextractTarget.id] === 'reextract'
        }
        onOpenChange={(open) => {
          if (!open) {
            setReextractTarget(null);
          }
        }}
        onConfirm={() => {
          if (!reextractTarget) {
            return;
          }
          const target = reextractTarget;
          void onConfirmReextract(target.id).then((outcome) => {
            if (
              outcome === 'success' ||
              outcome === 'duplicate' ||
              outcome === 'error'
            ) {
              setReextractTarget(null);
            }
          });
        }}
      />
    </VStack>
  );
}

// Re-export helpers for tests / callers that only need the action matrix.
export {evaluateActionLabel, formatSavedJobLabel} from './SavedJobDetail';

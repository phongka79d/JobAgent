/**
 * Selected saved-JD detail: source/extraction + persisted MatchResult (Plan 10).
 * Reuses MatchCard / ScoreBreakdown; does not duplicate score formatting maps.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {HStack} from '@astryxdesign/core/HStack';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {CachedResource, SavedJobActionKind} from './savedJobsState';
import {MatchCard} from './MatchCard';
import type {
  EvaluationCurrentness,
  SavedJobDetail as SavedJobDetailData,
  SavedJobListItem,
  SavedJobsSafeError,
} from './types';

export type SavedJobDetailProps = {
  job: SavedJobListItem;
  detail: CachedResource<SavedJobDetailData> | null;
  pendingKind: SavedJobActionKind | undefined;
  actionError: SavedJobsSafeError | undefined;
  onEvaluate: (jobId: string) => void;
  onRequestDelete: (job: SavedJobListItem) => void;
  onClearError: (jobId: string) => void;
  onRefreshDetail: (jobId: string) => void;
};

/** Concise Job display name for labels, confirmation, and a11y. */
export function formatSavedJobLabel(job: SavedJobListItem): string {
  const title = job.title?.trim() || '';
  const company = job.company?.trim() || '';
  if (title && company) {
    return `${title} · ${company}`;
  }
  if (title) {
    return title;
  }
  if (company) {
    return company;
  }
  return `Job ${job.id.slice(0, 8)}`;
}

/**
 * Evaluate CTA by currentness: none → evaluate, stale → re-evaluate, current → none.
 */
export function evaluateActionLabel(
  state: EvaluationCurrentness,
): string | null {
  if (state === 'none') {
    return 'Đánh giá với CV';
  }
  if (state === 'stale') {
    return 'Đánh giá lại';
  }
  return null;
}

export function SavedJobDetailView({
  job,
  detail,
  pendingKind,
  actionError,
  onEvaluate,
  onRequestDelete,
  onClearError,
  onRefreshDetail,
}: SavedJobDetailProps) {
  const isPending = pendingKind !== undefined;
  const isEvaluatePending = pendingKind === 'evaluate';
  const isDeletePending = pendingKind === 'delete';
  const evaluateLabel = evaluateActionLabel(job.evaluation_state);
  const data = detail?.data ?? null;
  const extraction = data?.extraction ?? null;
  const evaluation = data?.latest_evaluation ?? null;
  const jobLabel = formatSavedJobLabel(job);

  return (
    <VStack
      gap={2}
      className="jobagent-obs-detail"
      data-testid="jobagent-saved-job-detail"
      data-job-id={job.id}
      data-evaluation-state={job.evaluation_state}
    >
      <Text type="label" color="secondary" display="block">
        Selected JD
      </Text>
      <Text
        type="large"
        display="block"
        maxLines={2}
        hasTruncateTooltip
        data-testid="jobagent-saved-job-detail-title"
      >
        {jobLabel}
      </Text>

      <MetadataList
        columns="single"
        label={{position: 'top'}}
        data-testid="jobagent-saved-job-detail-meta"
      >
        <MetadataListItem label="Processing">
          {job.processing_status}
        </MetadataListItem>
        <MetadataListItem label="JD quality">
          {job.jd_quality ?? 'Unavailable'}
        </MetadataListItem>
        <MetadataListItem label="Source type">{job.source_type}</MetadataListItem>
        {job.source_url ? (
          <MetadataListItem label="Source URL">{job.source_url}</MetadataListItem>
        ) : null}
        <MetadataListItem label="Evaluation">
          {job.evaluation_state}
        </MetadataListItem>
      </MetadataList>

      {detail?.phase === 'loading' && !data ? (
        <Text
          type="supporting"
          color="secondary"
          as="p"
          data-testid="jobagent-saved-job-detail-loading"
        >
          Loading detail…
        </Text>
      ) : null}

      {detail?.phase === 'error' && detail.error ? (
        <Banner
          status="error"
          title="Detail unavailable"
          description={`${detail.error.summary} (${detail.error.code})`}
          container="section"
          data-testid="jobagent-saved-job-detail-error"
        />
      ) : null}

      {extraction ? (
        <VStack
          gap={1}
          width="100%"
          data-testid="jobagent-saved-job-extraction"
        >
          <Text type="label" as="p">
            Extraction
          </Text>
          <MetadataList columns="single" label={{position: 'start'}}>
            {extraction.title ? (
              <MetadataListItem label="Title">
                <Text type="body" maxLines={2} hasTruncateTooltip as="span">
                  {extraction.title}
                </Text>
              </MetadataListItem>
            ) : null}
            {extraction.company ? (
              <MetadataListItem label="Company">
                {extraction.company}
              </MetadataListItem>
            ) : null}
            <MetadataListItem label="Summary">
              <Text type="body" maxLines={4} hasTruncateTooltip as="span">
                {extraction.summary}
              </Text>
            </MetadataListItem>
            <MetadataListItem label="Seniority">
              {extraction.seniority}
            </MetadataListItem>
            <MetadataListItem label="Work mode">
              {extraction.work_mode}
            </MetadataListItem>
            {extraction.location ? (
              <MetadataListItem label="Location">
                {extraction.location}
              </MetadataListItem>
            ) : null}
          </MetadataList>
        </VStack>
      ) : null}

      {data?.raw_content ? (
        <VStack gap={1} width="100%" data-testid="jobagent-saved-job-source">
          <Text type="label" as="p">
            Source text
          </Text>
          <pre className="jobagent-obs-fulltext">{data.raw_content}</pre>
        </VStack>
      ) : null}

      {evaluation ? (
        <VStack
          gap={1}
          width="100%"
          data-testid="jobagent-saved-job-evaluation"
          data-evaluation-row-state={evaluation.evaluation_state}
        >
          {job.evaluation_state === 'stale' ? (
            <Banner
              status="warning"
              title="Cần đánh giá lại"
              description="Latest stored result is visible but not current for the active CV/profile context."
              container="section"
              data-testid="jobagent-saved-job-stale-banner"
            />
          ) : null}
          <MatchCard data={evaluation.result} />
        </VStack>
      ) : job.evaluation_state === 'none' ? (
        <Text
          type="supporting"
          color="secondary"
          as="p"
          data-testid="jobagent-saved-job-no-evaluation"
        >
          Chưa có kết quả đánh giá cho JD này.
        </Text>
      ) : null}

      {actionError ? (
        <Banner
          status="error"
          title="Action failed"
          description={`${actionError.summary} (${actionError.code})`}
          container="section"
          data-testid={`jobagent-saved-job-action-error-${job.id}`}
        />
      ) : null}

      <HStack
        gap={1}
        wrap="wrap"
        vAlign="center"
        className="jobagent-obs-row-actions"
        data-testid={`jobagent-saved-job-actions-${job.id}`}
      >
        {evaluateLabel ? (
          <Button
            label={evaluateLabel}
            variant="primary"
            size="sm"
            isDisabled={isPending}
            isLoading={isEvaluatePending}
            onClick={() => onEvaluate(job.id)}
            data-testid={`jobagent-saved-job-evaluate-${job.id}`}
          />
        ) : null}

        <Button
          label="Xoá JD"
          variant="destructive"
          size="sm"
          isDisabled={isPending}
          isLoading={isDeletePending}
          onClick={() => onRequestDelete(job)}
          data-testid={`jobagent-saved-job-delete-${job.id}`}
        />

        <Button
          label="Refresh detail"
          variant="ghost"
          size="sm"
          isDisabled={isPending}
          onClick={() => onRefreshDetail(job.id)}
          data-testid={`jobagent-saved-job-refresh-detail-${job.id}`}
        />

        {actionError ? (
          <Button
            label="Dismiss error"
            variant="ghost"
            size="sm"
            isDisabled={isPending}
            onClick={() => onClearError(job.id)}
            data-testid={`jobagent-saved-job-clear-error-${job.id}`}
          />
        ) : null}
      </HStack>
    </VStack>
  );
}

/**
 * Selected saved-JD detail: source/extraction + persisted MatchResult (Plan 10).
 * Plan 15: complete extraction groups, bounded collapsed evidence, re-extract CTA.
 * Reuses MatchCard / ScoreBreakdown; does not duplicate score formatting maps.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {HStack} from '@astryxdesign/core/HStack';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {CachedResource, SavedJobActionKind} from './savedJobsState';
import {MatchCard} from './MatchCard';
import {REEXTRACT_GRAPH_FAILURE_CODE} from './types';
import type {
  EvaluationCurrentness,
  JobPostExtractionView,
  JobSkillView,
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
  onRequestReextract: (job: SavedJobListItem) => void;
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

function formatExperienceRange(
  minYears: number | null,
  maxYears: number | null,
): string {
  if (minYears === null && maxYears === null) {
    return 'Not specified';
  }
  if (minYears !== null && maxYears !== null) {
    return `${minYears}–${maxYears} years`;
  }
  if (minYears !== null) {
    return `${minYears}+ years`;
  }
  return `Up to ${maxYears} years`;
}

function formatSkillConfidence(confidence: number): string {
  if (!Number.isFinite(confidence)) {
    return '—';
  }
  return confidence.toFixed(2);
}

function SkillListSection({
  title,
  skills,
  emptyLabel,
  testId,
}: {
  title: string;
  skills: JobSkillView[];
  emptyLabel: string;
  testId: string;
}) {
  return (
    <VStack gap={1} width="100%" data-testid={testId}>
      <Text type="label" as="p">
        {title}
      </Text>
      {skills.length === 0 ? (
        <Text type="supporting" color="secondary" as="p">
          {emptyLabel}
        </Text>
      ) : (
        <VStack gap={1} width="100%">
          {skills.map((item, index) => (
            <Text
              key={`${item.skill.canonical_key}-${index}`}
              type="body"
              as="p"
              data-testid={`${testId}-item-${index}`}
            >
              {item.skill.display_name}
              {' · '}
              {formatSkillConfidence(item.confidence)}
            </Text>
          ))}
        </VStack>
      )}
    </VStack>
  );
}

function ExtractionEvidenceSection({
  extraction,
}: {
  extraction: JobPostExtractionView;
}) {
  const entries: {label: string; quote: string}[] = [];
  for (const skill of extraction.required_skills) {
    for (const quote of skill.evidence) {
      entries.push({
        label: skill.skill.display_name,
        quote,
      });
    }
  }
  for (const skill of extraction.preferred_skills) {
    for (const quote of skill.evidence) {
      entries.push({
        label: skill.skill.display_name,
        quote,
      });
    }
  }

  return (
    <VStack
      gap={1}
      width="100%"
      data-testid="jobagent-saved-job-evidence"
    >
      <Collapsible
        defaultIsOpen={false}
        trigger={
          <Text type="label" as="span">
            Evidence ({entries.length})
          </Text>
        }
      >
        {entries.length === 0 ? (
          <Text
            type="supporting"
            color="secondary"
            as="p"
            data-testid="jobagent-saved-job-evidence-empty"
          >
            No evidence available
          </Text>
        ) : (
          <VStack gap={1} width="100%" data-testid="jobagent-saved-job-evidence-list">
            {entries.map((entry, index) => (
              <VStack
                key={`${entry.label}-${index}`}
                gap={0}
                width="100%"
                data-testid={`jobagent-saved-job-evidence-item-${index}`}
              >
                <Text type="supporting" color="secondary" as="p">
                  {entry.label}
                </Text>
                <Text type="body" as="p" maxLines={4} hasTruncateTooltip>
                  {entry.quote}
                </Text>
              </VStack>
            ))}
          </VStack>
        )}
      </Collapsible>
    </VStack>
  );
}

function ExtractionGroups({extraction}: {extraction: JobPostExtractionView}) {
  const summaryText =
    extraction.summary.trim() === ''
      ? 'No summary available'
      : extraction.summary;

  return (
    <VStack
      gap={2}
      width="100%"
      data-testid="jobagent-saved-job-extraction"
    >
      <Text type="label" as="p">
        Extraction
      </Text>

      <VStack
        gap={1}
        width="100%"
        data-testid="jobagent-saved-job-extraction-metadata"
      >
        <MetadataList columns="single" label={{position: 'start'}}>
          <MetadataListItem label="Title">
            <Text type="body" maxLines={2} hasTruncateTooltip as="span">
              {extraction.title?.trim() || 'Not specified'}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Company">
            {extraction.company?.trim() || 'Not specified'}
          </MetadataListItem>
          <MetadataListItem label="Summary">
            <Text type="body" maxLines={4} hasTruncateTooltip as="span">
              {summaryText}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Seniority">
            {extraction.seniority}
          </MetadataListItem>
          <MetadataListItem label="Experience">
            {formatExperienceRange(
              extraction.min_experience_years,
              extraction.max_experience_years,
            )}
          </MetadataListItem>
          <MetadataListItem label="Location">
            {extraction.location?.trim() || 'Not specified'}
          </MetadataListItem>
          <MetadataListItem label="Work mode">
            {extraction.work_mode}
          </MetadataListItem>
          <MetadataListItem label="Extraction confidence">
            {formatSkillConfidence(extraction.extraction_confidence)}
          </MetadataListItem>
        </MetadataList>
      </VStack>

      <VStack
        gap={1}
        width="100%"
        data-testid="jobagent-saved-job-responsibilities"
      >
        <Text type="label" as="p">
          Responsibilities
        </Text>
        {extraction.responsibilities.length === 0 ? (
          <Text
            type="supporting"
            color="secondary"
            as="p"
            data-testid="jobagent-saved-job-responsibilities-empty"
          >
            No responsibilities extracted
          </Text>
        ) : (
          <VStack gap={1} width="100%">
            {extraction.responsibilities.map((item, index) => (
              <Text
                key={`resp-${index}`}
                type="body"
                as="p"
                data-testid={`jobagent-saved-job-responsibility-${index}`}
              >
                {item}
              </Text>
            ))}
          </VStack>
        )}
      </VStack>

      <SkillListSection
        title="Required skills"
        skills={extraction.required_skills}
        emptyLabel="No required skills extracted"
        testId="jobagent-saved-job-required-skills"
      />

      <SkillListSection
        title="Preferred skills"
        skills={extraction.preferred_skills}
        emptyLabel="No preferred skills extracted"
        testId="jobagent-saved-job-preferred-skills"
      />

      <ExtractionEvidenceSection extraction={extraction} />
    </VStack>
  );
}

export function SavedJobDetailView({
  job,
  detail,
  pendingKind,
  actionError,
  onEvaluate,
  onRequestDelete,
  onRequestReextract,
  onClearError,
  onRefreshDetail,
}: SavedJobDetailProps) {
  const isPending = pendingKind !== undefined;
  const isEvaluatePending = pendingKind === 'evaluate';
  const isDeletePending = pendingKind === 'delete';
  const isReextractPending = pendingKind === 'reextract';
  const evaluateLabel = evaluateActionLabel(job.evaluation_state);
  const data = detail?.data ?? null;
  const extraction = data?.extraction ?? null;
  const evaluation = data?.latest_evaluation ?? null;
  const jobLabel = formatSavedJobLabel(job);
  const isGraphWarning =
    actionError?.code === REEXTRACT_GRAPH_FAILURE_CODE;

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
        <ExtractionGroups extraction={extraction} />
      ) : data && detail?.phase !== 'loading' ? (
        <Text
          type="supporting"
          color="secondary"
          as="p"
          data-testid="jobagent-saved-job-extraction-empty"
        >
          No structured extraction available
        </Text>
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
          status={isGraphWarning ? 'warning' : 'error'}
          title={
            isGraphWarning
              ? 'Graph rebuild required'
              : 'Action failed'
          }
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
          label="Re-extract JD"
          variant="secondary"
          size="sm"
          isDisabled={isPending}
          isLoading={isReextractPending}
          onClick={() => onRequestReextract(job)}
          data-testid={`jobagent-saved-job-reextract-${job.id}`}
        />

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

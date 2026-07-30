/**
 * Selected saved-JD detail: source/extraction + persisted MatchResult (Plan 10).
 * Plan 15: complete extraction groups, bounded collapsed evidence, re-extract CTA.
 * Reuses MatchCard / ScoreBreakdown; does not duplicate score formatting maps.
 */

import {useState} from 'react';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {HStack} from '@astryxdesign/core/HStack';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {Tab, TabList} from '@astryxdesign/core/TabList';
import {VStack} from '@astryxdesign/core/VStack';

import type {CachedResource, SavedJobActionKind} from './savedJobsState';
import {JOB_COPY, savedJobDisplayLabel} from './copy';
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
  canCreateTailoredCv?: boolean;
  isTailoringPending?: boolean;
  onCreateTailoredCv?: (jobId: string) => void;
};

type SavedJobDetailTab = 'comparison' | 'overview' | 'source';

/** Concise Job display name for labels, confirmation, and a11y. */
export function formatSavedJobLabel(job: SavedJobListItem): string {
  return savedJobDisplayLabel(job);
}

function processingStatusLabel(
  status: SavedJobListItem['processing_status'],
): string {
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

function qualityStatusLabel(quality: SavedJobListItem['jd_quality']): string {
  switch (quality) {
    case 'full':
      return 'Complete';
    case 'partial':
      return 'Partial';
    case 'unscorable':
      return 'Not scorable';
    default:
      return 'Not available';
  }
}

function sourceTypeLabel(sourceType: SavedJobListItem['source_type']): string {
  return sourceType === 'url' ? 'Link' : 'Text';
}

function evaluationStatusLabel(state: EvaluationCurrentness): string {
  switch (state) {
    case 'current':
      return 'Current';
    case 'stale':
      return 'Needs re-evaluation';
    case 'none':
    default:
      return 'Not evaluated';
  }
}

/**
 * Evaluate CTA by currentness: none → evaluate, stale → re-evaluate, current → none.
 */
export function evaluateActionLabel(
  state: EvaluationCurrentness,
): string | null {
  if (state === 'none') {
    return 'Evaluate with CV';
  }
  if (state === 'stale') {
    return 'Re-evaluate';
  }
  return null;
}

function formatExperienceRange(
  minYears: number | null,
  maxYears: number | null,
): string {
  if (minYears === null && maxYears === null) {
    return 'Unknown';
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
        {JOB_COPY.extractionHeading}
      </Text>

      <VStack
        gap={1}
        width="100%"
        data-testid="jobagent-saved-job-extraction-metadata"
      >
        <MetadataList columns="single" label={{position: 'start'}}>
          <MetadataListItem label="Role">
            <Text type="body" maxLines={2} hasTruncateTooltip as="span">
              {extraction.title?.trim() || 'Unknown'}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Company">
            {extraction.company?.trim() || 'Unknown'}
          </MetadataListItem>
          <MetadataListItem label="Summary">
            <Text type="body" maxLines={4} hasTruncateTooltip as="span">
              {summaryText}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Seniority">
            {extraction.seniority === 'unknown'
              ? 'Unknown'
              : extraction.seniority}
          </MetadataListItem>
          <MetadataListItem label="Experience">
            {formatExperienceRange(
              extraction.min_experience_years,
              extraction.max_experience_years,
            )}
          </MetadataListItem>
          <MetadataListItem label="Location">
            {extraction.location?.trim() || 'Unknown'}
          </MetadataListItem>
          <MetadataListItem label="Work mode">
            {extraction.work_mode === 'unknown'
              ? 'Unknown'
              : extraction.work_mode}
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
            No responsibilities were extracted
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
        emptyLabel="No required skills were extracted"
        testId="jobagent-saved-job-required-skills"
      />

      <SkillListSection
        title="Preferred skills"
        skills={extraction.preferred_skills}
        emptyLabel="No preferred skills were extracted"
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
  canCreateTailoredCv = false,
  isTailoringPending = false,
  onCreateTailoredCv,
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
  const [activeTab, setActiveTab] =
    useState<SavedJobDetailTab>('comparison');

  return (
    <VStack
      gap={2}
      className="jobagent-saved-job-detail"
      data-testid="jobagent-saved-job-detail"
      data-job-id={job.id}
      data-evaluation-state={job.evaluation_state}
    >
      <Text type="label" color="secondary" display="block">
        Selected job
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
          {processingStatusLabel(job.processing_status)}
        </MetadataListItem>
        <MetadataListItem label="JD quality">
          {qualityStatusLabel(job.jd_quality)}
        </MetadataListItem>
        <MetadataListItem label="Source type">
          {sourceTypeLabel(job.source_type)}
        </MetadataListItem>
        {job.source_url ? (
          <MetadataListItem label="Source URL">{job.source_url}</MetadataListItem>
        ) : null}
        <MetadataListItem label="Evaluation">
          {evaluationStatusLabel(job.evaluation_state)}
        </MetadataListItem>
      </MetadataList>

      <HStack
        gap={1}
        wrap="wrap"
        vAlign="center"
        className="jobagent-saved-job-row-actions"
        role="group"
        aria-label={JOB_COPY.actions}
        data-testid={`jobagent-saved-job-actions-${job.id}`}
      >
        {canCreateTailoredCv &&
        job.processing_status === 'processed' &&
        (job.jd_quality === 'full' || job.jd_quality === 'partial') &&
        onCreateTailoredCv ? (
          <Button
            label="Create tailored CV"
            variant="primary"
            size="sm"
            isDisabled={isPending || isTailoringPending}
            isLoading={isTailoringPending}
            onClick={() => onCreateTailoredCv(job.id)}
            data-testid={`jobagent-saved-job-tailor-${job.id}`}
          />
        ) : null}
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
          label="Re-extract"
          variant="secondary"
          size="sm"
          isDisabled={isPending}
          isLoading={isReextractPending}
          onClick={() => onRequestReextract(job)}
          data-testid={`jobagent-saved-job-reextract-${job.id}`}
        />

        <Button
          label="Refresh"
          variant="ghost"
          size="sm"
          isDisabled={isPending}
          onClick={() => onRefreshDetail(job.id)}
          data-testid={`jobagent-saved-job-refresh-detail-${job.id}`}
        />

        <Button
          label={JOB_COPY.deleteJob}
          variant="destructive"
          size="sm"
          isDisabled={isPending}
          isLoading={isDeletePending}
          onClick={() => onRequestDelete(job)}
          data-testid={`jobagent-saved-job-delete-${job.id}`}
        />

        {actionError ? (
          <Button
            label="Dismiss message"
            variant="ghost"
            size="sm"
            isDisabled={isPending}
            onClick={() => onClearError(job.id)}
            data-testid={`jobagent-saved-job-clear-error-${job.id}`}
          />
        ) : null}
      </HStack>

      <TabList
        role="tablist"
        aria-label="Saved job details"
        value={activeTab}
        onChange={(value) => setActiveTab(value as SavedJobDetailTab)}
        size="sm"
        layout="fill"
        hasDivider
      >
        <Tab
          value="comparison"
          label="CV match"
          role="tab"
          aria-selected={activeTab === 'comparison'}
        />
        <Tab
          value="overview"
          label={JOB_COPY.overviewTab}
          role="tab"
          aria-selected={activeTab === 'overview'}
        />
        <Tab
          value="source"
          label={JOB_COPY.sourceTab}
          role="tab"
          aria-selected={activeTab === 'source'}
        />
      </TabList>

      {detail?.phase === 'loading' && !data ? (
        <Text
          type="supporting"
          color="secondary"
          as="p"
          data-testid="jobagent-saved-job-detail-loading"
        >
          Loading details…
        </Text>
      ) : null}

      {detail?.phase === 'error' && detail.error ? (
        <Banner
          status="error"
          title="Unable to load details"
          description={detail.error.summary}
          container="section"
          data-testid="jobagent-saved-job-detail-error"
        />
      ) : null}

      {activeTab === 'overview' && extraction ? (
        <ExtractionGroups extraction={extraction} />
      ) : activeTab === 'overview' && data && detail?.phase !== 'loading' ? (
        <Text
          type="supporting"
          color="secondary"
          as="p"
          data-testid="jobagent-saved-job-extraction-empty"
        >
          No structured extraction is available
        </Text>
      ) : null}

      {activeTab === 'source' && data?.raw_content ? (
        <VStack gap={1} width="100%" data-testid="jobagent-saved-job-source">
          <Text type="label" as="p">
            Source text
          </Text>
          <pre className="jobagent-saved-job-fulltext">{data.raw_content}</pre>
        </VStack>
      ) : null}

      {activeTab === 'source' && data && !data.raw_content ? (
        <Text type="supporting" color="secondary" as="p">
          No source text is available.
        </Text>
      ) : null}

      {activeTab === 'comparison' && evaluation ? (
        <VStack
          gap={1}
          width="100%"
          data-testid="jobagent-saved-job-evaluation"
          data-evaluation-row-state={evaluation.evaluation_state}
        >
          {job.evaluation_state === 'stale' ? (
            <Banner
              status="warning"
              title="Re-evaluation needed"
              description="The saved result is still visible but no longer matches the current CV or profile."
              container="section"
              data-testid="jobagent-saved-job-stale-banner"
            />
          ) : null}
          <MatchCard data={evaluation.result} showJobMetadata={false} />
        </VStack>
      ) : activeTab === 'comparison' && job.evaluation_state === 'none' ? (
        <Text
          type="supporting"
          color="secondary"
          as="p"
          data-testid="jobagent-saved-job-no-evaluation"
        >
          No CV match result is available for this job.
        </Text>
      ) : null}

      {actionError ? (
        <Banner
          status={isGraphWarning ? 'warning' : 'error'}
          title={
            isGraphWarning
              ? 'Related data needs recovery'
              : 'Action failed'
          }
          description={actionError.summary}
          container="section"
          data-testid={`jobagent-saved-job-action-error-${job.id}`}
        />
      ) : null}

    </VStack>
  );
}

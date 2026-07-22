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

type SavedJobDetailTab = 'comparison' | 'overview' | 'source';

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

function processingStatusLabel(
  status: SavedJobListItem['processing_status'],
): string {
  switch (status) {
    case 'processed':
      return 'Đã xử lý';
    case 'processing':
      return 'Đang xử lý';
    case 'failed':
      return 'Xử lý lỗi';
    case 'received':
    default:
      return 'Đã tiếp nhận';
  }
}

function qualityStatusLabel(quality: SavedJobListItem['jd_quality']): string {
  switch (quality) {
    case 'full':
      return 'Đầy đủ';
    case 'partial':
      return 'Một phần';
    case 'unscorable':
      return 'Chưa thể chấm';
    default:
      return 'Chưa có';
  }
}

function sourceTypeLabel(sourceType: SavedJobListItem['source_type']): string {
  return sourceType === 'url' ? 'Đường dẫn' : 'Văn bản';
}

function evaluationStatusLabel(state: EvaluationCurrentness): string {
  switch (state) {
    case 'current':
      return 'Hiện tại';
    case 'stale':
      return 'Cần đánh giá lại';
    case 'none':
    default:
      return 'Chưa đánh giá';
  }
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
    return 'Chưa xác định';
  }
  if (minYears !== null && maxYears !== null) {
    return `${minYears}–${maxYears} năm`;
  }
  if (minYears !== null) {
    return `${minYears}+ năm`;
  }
  return `Tối đa ${maxYears} năm`;
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
            Bằng chứng ({entries.length})
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
            Không có bằng chứng
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
      ? 'Không có bản tóm tắt'
      : extraction.summary;

  return (
    <VStack
      gap={2}
      width="100%"
      data-testid="jobagent-saved-job-extraction"
    >
      <Text type="label" as="p">
        Thông tin JD
      </Text>

      <VStack
        gap={1}
        width="100%"
        data-testid="jobagent-saved-job-extraction-metadata"
      >
        <MetadataList columns="single" label={{position: 'start'}}>
          <MetadataListItem label="Vị trí">
            <Text type="body" maxLines={2} hasTruncateTooltip as="span">
              {extraction.title?.trim() || 'Chưa xác định'}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Công ty">
            {extraction.company?.trim() || 'Chưa xác định'}
          </MetadataListItem>
          <MetadataListItem label="Tóm tắt">
            <Text type="body" maxLines={4} hasTruncateTooltip as="span">
              {summaryText}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Cấp bậc">
            {extraction.seniority === 'unknown'
              ? 'Chưa xác định'
              : extraction.seniority}
          </MetadataListItem>
          <MetadataListItem label="Kinh nghiệm">
            {formatExperienceRange(
              extraction.min_experience_years,
              extraction.max_experience_years,
            )}
          </MetadataListItem>
          <MetadataListItem label="Địa điểm">
            {extraction.location?.trim() || 'Chưa xác định'}
          </MetadataListItem>
          <MetadataListItem label="Hình thức làm việc">
            {extraction.work_mode === 'unknown'
              ? 'Chưa xác định'
              : extraction.work_mode}
          </MetadataListItem>
          <MetadataListItem label="Độ tin cậy trích xuất">
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
          Trách nhiệm
        </Text>
        {extraction.responsibilities.length === 0 ? (
          <Text
            type="supporting"
            color="secondary"
            as="p"
            data-testid="jobagent-saved-job-responsibilities-empty"
          >
            Không trích xuất được trách nhiệm
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
        title="Kỹ năng bắt buộc"
        skills={extraction.required_skills}
        emptyLabel="Không trích xuất được kỹ năng bắt buộc"
        testId="jobagent-saved-job-required-skills"
      />

      <SkillListSection
        title="Kỹ năng ưu tiên"
        skills={extraction.preferred_skills}
        emptyLabel="Không trích xuất được kỹ năng ưu tiên"
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
  const [activeTab, setActiveTab] =
    useState<SavedJobDetailTab>('comparison');

  return (
    <VStack
      gap={2}
      className="jobagent-obs-detail"
      data-testid="jobagent-saved-job-detail"
      data-job-id={job.id}
      data-evaluation-state={job.evaluation_state}
    >
      <Text type="label" color="secondary" display="block">
        JD đã chọn
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
        <MetadataListItem label="Xử lý">
          {processingStatusLabel(job.processing_status)}
        </MetadataListItem>
        <MetadataListItem label="Chất lượng JD">
          {qualityStatusLabel(job.jd_quality)}
        </MetadataListItem>
        <MetadataListItem label="Loại nguồn">
          {sourceTypeLabel(job.source_type)}
        </MetadataListItem>
        {job.source_url ? (
          <MetadataListItem label="URL nguồn">{job.source_url}</MetadataListItem>
        ) : null}
        <MetadataListItem label="Đánh giá">
          {evaluationStatusLabel(job.evaluation_state)}
        </MetadataListItem>
      </MetadataList>

      <HStack
        gap={1}
        wrap="wrap"
        vAlign="center"
        className="jobagent-obs-row-actions"
        role="group"
        aria-label="Thao tác JD"
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
          label="Trích xuất lại"
          variant="secondary"
          size="sm"
          isDisabled={isPending}
          isLoading={isReextractPending}
          onClick={() => onRequestReextract(job)}
          data-testid={`jobagent-saved-job-reextract-${job.id}`}
        />

        <Button
          label="Làm mới"
          variant="ghost"
          size="sm"
          isDisabled={isPending}
          onClick={() => onRefreshDetail(job.id)}
          data-testid={`jobagent-saved-job-refresh-detail-${job.id}`}
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

        {actionError ? (
          <Button
            label="Đóng thông báo"
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
        aria-label="Chi tiết JD"
        value={activeTab}
        onChange={(value) => setActiveTab(value as SavedJobDetailTab)}
        size="sm"
        layout="fill"
        hasDivider
      >
        <Tab
          value="comparison"
          label="Đối chiếu CV"
          role="tab"
          aria-selected={activeTab === 'comparison'}
        />
        <Tab
          value="overview"
          label="Tổng quan JD"
          role="tab"
          aria-selected={activeTab === 'overview'}
        />
        <Tab
          value="source"
          label="Nội dung gốc"
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
          Đang tải chi tiết…
        </Text>
      ) : null}

      {detail?.phase === 'error' && detail.error ? (
        <Banner
          status="error"
          title="Không thể tải chi tiết"
          description={`${detail.error.summary} (${detail.error.code})`}
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
          Không có dữ liệu trích xuất có cấu trúc
        </Text>
      ) : null}

      {activeTab === 'source' && data?.raw_content ? (
        <VStack gap={1} width="100%" data-testid="jobagent-saved-job-source">
          <Text type="label" as="p">
            Nội dung gốc
          </Text>
          <pre className="jobagent-obs-fulltext">{data.raw_content}</pre>
        </VStack>
      ) : null}

      {activeTab === 'source' && data && !data.raw_content ? (
        <Text type="supporting" color="secondary" as="p">
          Không có nội dung nguồn.
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
              title="Cần đánh giá lại"
              description="Kết quả đã lưu vẫn được hiển thị nhưng không còn khớp với CV hoặc hồ sơ hiện tại."
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
          Chưa có kết quả đối chiếu CV cho JD này.
        </Text>
      ) : null}

      {actionError ? (
        <Banner
          status={isGraphWarning ? 'warning' : 'error'}
          title={
            isGraphWarning
              ? 'Cần dựng lại đồ thị'
              : 'Thao tác thất bại'
          }
          description={`${actionError.summary} (${actionError.code})`}
          container="section"
          data-testid={`jobagent-saved-job-action-error-${job.id}`}
        />
      ) : null}

    </VStack>
  );
}

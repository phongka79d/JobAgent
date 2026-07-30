/**
 * Compact saved-job result card (Plan 5 §7.9 / Master §15.3).
 * Renders durable save_job ToolResult projection via public Astryx Card,
 * MetadataList, and Badge. Badge is only for processing status and JD quality.
 * No raw JD, embeddings, ranking, or raw layout.
 */

import {Badge} from '@astryxdesign/core/Badge';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Link} from '@astryxdesign/core/Link';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import {
  NEO4J_SYNC_FAILED_CODE,
  type CompactSaveJobResult,
  type JobJdQuality,
  type JobProcessingStatus,
} from './types';

export type SavedJobCardProps = {
  data: CompactSaveJobResult;
  /** Concise ToolResult.summary when present. */
  summary?: string | null;
  /** Stable tool/error code (e.g. NEO4J_SYNC_FAILED). */
  errorCode?: string | null;
};

function processingBadgeVariant(
  status: JobProcessingStatus,
): 'neutral' | 'info' | 'success' | 'warning' | 'error' {
  switch (status) {
    case 'processed':
      return 'success';
    case 'failed':
      return 'error';
    case 'processing':
      return 'info';
    case 'received':
    default:
      return 'neutral';
  }
}

function qualityBadgeVariant(
  quality: JobJdQuality,
): 'neutral' | 'info' | 'success' | 'warning' {
  switch (quality) {
    case 'full':
      return 'success';
    case 'partial':
      return 'info';
    case 'unscorable':
      return 'warning';
    default:
      return 'neutral';
  }
}

function outcomeLabel(outcome: CompactSaveJobResult['outcome']): string {
  switch (outcome) {
    case 'created':
      return 'Created';
    case 'returned':
      return 'Returned existing';
    case 'retried':
      return 'Retried in place';
    default:
      return outcome;
  }
}

/**
 * Concise success/failure summary for the card footer.
 * NEO4J_SYNC_FAILED keeps processed SQLite truth visible and never implies
 * graph or ranking success.
 */
export function buildSavedJobSummaryLines(
  data: CompactSaveJobResult,
  summary: string | null | undefined,
  errorCode: string | null | undefined,
): string[] {
  const lines: string[] = [];
  const code = errorCode ?? data.failureCode;
  const isSyncFailed =
    code === NEO4J_SYNC_FAILED_CODE || data.syncOk === false;

  if (isSyncFailed) {
    lines.push(
      'The saved job is available, but related data could not be refreshed.',
    );
    // Explicit partial success: never claim related-data refresh succeeded.
    lines.push('Related data remains unavailable until recovery succeeds.');
    return lines;
  }

  if (data.processingStatus === 'failed') {
    lines.push('The saved job could not be processed.');
    if (data.pasteInstruction) {
      lines.push(data.pasteInstruction);
    }
    return lines;
  }

  if (summary && summary.trim() !== '') {
    lines.push(summary.trim());
  } else {
    lines.push(
      `${outcomeLabel(data.outcome)} — ${processingStatusLabel(data.processingStatus)}`,
    );
  }

  return lines;
}

function processingStatusLabel(status: JobProcessingStatus): string {
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

function qualityLabel(quality: JobJdQuality): string {
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

export function SavedJobCard({data, summary, errorCode}: SavedJobCardProps) {
  const lines = buildSavedJobSummaryLines(data, summary, errorCode);
  const heading = data.displayLabel?.trim() || 'Saved job';
  const code = errorCode ?? data.failureCode;
  const isSyncFailed =
    code === NEO4J_SYNC_FAILED_CODE || data.syncOk === false;

  return (
    <Card
      padding={3}
      variant={
        data.processingStatus === 'failed' || isSyncFailed ? 'muted' : 'default'
      }
      maxWidth="100%"
      data-testid="jobagent-saved-job-card"
      data-job-id={data.jobId}
      data-outcome={data.outcome}
      data-processing-status={data.processingStatus}
      data-sync-ok={
        data.syncOk === null ? 'null' : data.syncOk ? 'true' : 'false'
      }
    >
      <VStack gap={2} width="100%">
        <Heading level={4}>{heading}</Heading>
        <HStack gap={1}>
          <Badge
            variant={processingBadgeVariant(data.processingStatus)}
            label={processingStatusLabel(data.processingStatus)}
            data-testid="jobagent-job-processing-badge"
          />
          {data.jdQuality ? (
            <Badge
              variant={qualityBadgeVariant(data.jdQuality)}
              label={qualityLabel(data.jdQuality)}
              data-testid="jobagent-job-quality-badge"
            />
          ) : null}
        </HStack>
        <MetadataList
          columns="single"
          label={{position: 'start'}}
          data-testid="jobagent-saved-job-metadata"
        >
          {data.company ? (
            <MetadataListItem label="Company">{data.company}</MetadataListItem>
          ) : null}
          {data.title ? (
            <MetadataListItem label="Title">{data.title}</MetadataListItem>
          ) : null}
          {data.sourceUrl ? (
            <MetadataListItem label="Source">
              <Link href={data.sourceUrl} isExternalLink hasUnderline>
                {data.sourceUrl}
              </Link>
            </MetadataListItem>
          ) : null}
          <MetadataListItem label="Outcome">
            {outcomeLabel(data.outcome)}
          </MetadataListItem>
          <MetadataListItem label="Saved status">
            {data.sqliteCommitted ? 'Saved' : 'Not saved'}
          </MetadataListItem>
          {isSyncFailed ? (
            <MetadataListItem label="Related data">
              Needs recovery
            </MetadataListItem>
          ) : data.syncOk === true ? (
            <MetadataListItem label="Related data">Available</MetadataListItem>
          ) : null}
        </MetadataList>
        {lines.map((line, index) => (
          <Text
            key={`${index}:${line.slice(0, 32)}`}
            type="supporting"
            color="secondary"
            as="p"
          >
            {line}
          </Text>
        ))}
      </VStack>
    </Card>
  );
}

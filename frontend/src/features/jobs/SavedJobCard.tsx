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

  if (summary && summary.trim() !== '') {
    lines.push(summary.trim());
  }

  if (isSyncFailed) {
    if (!lines.some((l) => /neo4j|sync failed|rebuild/i.test(l))) {
      lines.push(
        'Job saved to SQLite but Neo4j graph sync failed; rebuild graph from SQLite.',
      );
    }
    if (data.rebuildInstruction) {
      lines.push(data.rebuildInstruction);
    }
    // Explicit non-success for graph path — never claim ranking/graph success.
    lines.push('Graph projection unavailable until rebuild succeeds.');
  } else if (data.processingStatus === 'failed') {
    if (code && !lines.some((l) => l.includes(code))) {
      lines.push(`Ingestion failed (${code})`);
    }
    if (data.pasteInstruction) {
      lines.push(data.pasteInstruction);
    }
  } else if (lines.length === 0) {
    lines.push(
      `${outcomeLabel(data.outcome)} — ${data.processingStatus}` +
        (data.jdQuality ? `/${data.jdQuality}` : ''),
    );
  }

  return lines;
}

export function SavedJobCard({data, summary, errorCode}: SavedJobCardProps) {
  const lines = buildSavedJobSummaryLines(data, summary, errorCode);
  const heading =
    data.title?.trim() ||
    data.company?.trim() ||
    'Saved job';
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
            label={data.processingStatus}
            data-testid="jobagent-job-processing-badge"
          />
          {data.jdQuality ? (
            <Badge
              variant={qualityBadgeVariant(data.jdQuality)}
              label={data.jdQuality}
              data-testid="jobagent-job-quality-badge"
            />
          ) : null}
        </HStack>
        <MetadataList
          columns="single"
          label={{position: 'start'}}
          data-testid="jobagent-saved-job-metadata"
        >
          <MetadataListItem label="Job ID">{data.jobId}</MetadataListItem>
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
          <MetadataListItem label="SQLite">
            {data.sqliteCommitted ? 'Committed' : 'Not committed'}
          </MetadataListItem>
          {isSyncFailed ? (
            <MetadataListItem label="Graph">
              Sync failed (SQLite remains authoritative)
            </MetadataListItem>
          ) : data.syncOk === true ? (
            <MetadataListItem label="Graph">Synced</MetadataListItem>
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

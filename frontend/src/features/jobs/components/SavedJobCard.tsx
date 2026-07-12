/**
 * Saved-Job chat card: Card + MetadataList + Badge for enumerated status.
 * Documented Astryx APIs only — no raw layout divs or hard-coded visual values.
 */

import { Badge } from "@astryxdesign/core/Badge";
import { Card } from "@astryxdesign/core/Card";
import { HStack } from "@astryxdesign/core/HStack";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import {
  formatJobStatusLabel,
  type SavedJobCardPayload,
} from "../contracts";

export interface SavedJobCardProps {
  readonly job: SavedJobCardPayload;
  readonly "data-testid"?: string;
}

function qualityBadgeVariant(
  quality: string | null,
): "success" | "warning" | "error" | "neutral" {
  switch ((quality ?? "").toLowerCase()) {
    case "full":
      return "success";
    case "partial":
      return "warning";
    case "unscorable":
      return "error";
    default:
      return "neutral";
  }
}

function duplicateLabel(outcome: string): string | null {
  switch (outcome) {
    case "none":
      return null;
    case "exact":
      return "Exact duplicate";
    case "ignored_normalized":
      return "Normalized duplicate";
    case "force_new":
      return "Separate position";
    default:
      return formatJobStatusLabel(outcome);
  }
}

function graphLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Graph pending";
    case "synced":
      return "Graph synced";
    case "failed":
    case "sync_failed":
      return "Graph sync failed";
    case "not_required":
      return "Graph not required";
    default:
      return formatJobStatusLabel(status);
  }
}

/**
 * Renders only typed display-safe Job fields. Never shows raw JD, secrets,
 * tool arguments, stack traces, or score/match presentation.
 */
export function SavedJobCard({
  job,
  "data-testid": testId = "saved-job-card",
}: SavedJobCardProps) {
  const heading =
    job.title?.trim() ||
    job.company?.trim() ||
    "Saved job";
  const companyLine =
    job.company && job.title ? job.company : null;
  const duplicate = duplicateLabel(job.duplicateOutcome);
  const reasons =
    job.qualityReasonsPreview.length > 0
      ? job.qualityReasonsPreview.join("; ")
      : null;

  return (
    <Card padding={4} data-testid={testId} data-job-id={job.jobId}>
      <VStack gap={3}>
        <VStack gap={1}>
          <Text type="body" as="p" data-testid="saved-job-title">
            {heading}
          </Text>
          {companyLine ? (
            <Text type="supporting" as="p" data-testid="saved-job-company">
              {companyLine}
            </Text>
          ) : null}
        </VStack>

        <HStack gap={2} wrap="wrap" data-testid="saved-job-badges">
          {job.jdQuality ? (
            <Badge
              variant={qualityBadgeVariant(job.jdQuality)}
              label={formatJobStatusLabel(job.jdQuality)}
            />
          ) : null}
          {duplicate ? (
            <Badge variant="info" label={duplicate} />
          ) : null}
          <Badge variant="neutral" label={graphLabel(job.graphSyncStatus)} />
          {job.processingResult === "failed" ? (
            <Badge variant="error" label="Processing failed" />
          ) : null}
        </HStack>

        <MetadataList
          columns="single"
          label={{ position: "start" }}
          data-testid="saved-job-metadata"
        >
          {job.location ? (
            <MetadataListItem label="Location">{job.location}</MetadataListItem>
          ) : null}
          {job.workMode ? (
            <MetadataListItem label="Work mode">
              {formatJobStatusLabel(job.workMode)}
            </MetadataListItem>
          ) : null}
          {job.employmentType ? (
            <MetadataListItem label="Employment">
              {formatJobStatusLabel(job.employmentType)}
            </MetadataListItem>
          ) : null}
          {reasons ? (
            <MetadataListItem label="Quality notes">{reasons}</MetadataListItem>
          ) : null}
          {job.sourceUrl ? (
            <MetadataListItem label="Source">{job.sourceUrl}</MetadataListItem>
          ) : null}
          <MetadataListItem label="Job ID">{job.jobId}</MetadataListItem>
        </MetadataList>
      </VStack>
    </Card>
  );
}

/**
 * Match result chat card: Card + MetadataList + skill evidence + ScoreBreakdown.
 * Documented Astryx APIs only — no raw layout divs or hard-coded visual values.
 */

import { Badge } from "@astryxdesign/core/Badge";
import { Card } from "@astryxdesign/core/Card";
import { HStack } from "@astryxdesign/core/HStack";
import { Link } from "@astryxdesign/core/Link";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import {
  formatJobStatusLabel,
  formatMatchScore,
  type MatchResultItem,
  type MatchSkillPath,
} from "../contracts";
import { ScoreBreakdown } from "./ScoreBreakdown";

export interface MatchCardProps {
  readonly match: MatchResultItem;
  readonly "data-testid"?: string;
}

function skillNames(skills: readonly MatchSkillPath[]): string {
  return skills.map((s) => s.displayName).join(", ");
}

function qualityBadgeVariant(
  quality: MatchResultItem["quality"],
): "success" | "warning" {
  return quality === "full" ? "success" : "warning";
}

/**
 * Renders one validated top-match result. Never shows raw JD/CV, vectors,
 * provider data, provisional paths, or unsafe URLs.
 */
export function MatchCard({
  match,
  "data-testid": testId = "match-card",
}: MatchCardProps) {
  const heading =
    match.title?.trim() || match.company?.trim() || "Matched job";
  const companyLine =
    match.company && match.title ? match.company : null;
  const scoreLabel = formatMatchScore(match.finalScore);

  return (
    <Card padding={4} data-testid={testId} data-job-id={match.jobId}>
      <VStack gap={3}>
        <VStack gap={1}>
          <Text type="body" as="p" data-testid={`${testId}-title`}>
            {heading}
          </Text>
          {companyLine ? (
            <Text type="supporting" as="p" data-testid={`${testId}-company`}>
              {companyLine}
            </Text>
          ) : null}
        </VStack>

        <HStack gap={2} wrap="wrap" data-testid={`${testId}-badges`}>
          <Badge
            variant="info"
            label={`Score ${scoreLabel}`}
            data-testid={`${testId}-score`}
          />
          <Badge
            variant={qualityBadgeVariant(match.quality)}
            label={formatJobStatusLabel(match.quality)}
          />
        </HStack>

        <MetadataList
          columns="single"
          label={{ position: "start" }}
          data-testid={`${testId}-metadata`}
        >
          {match.location ? (
            <MetadataListItem label="Location">{match.location}</MetadataListItem>
          ) : null}
          {match.workMode ? (
            <MetadataListItem label="Work mode">
              {formatJobStatusLabel(match.workMode)}
            </MetadataListItem>
          ) : null}
          <MetadataListItem label="Final score">{scoreLabel}</MetadataListItem>
          {match.matchedRequiredSkills.length > 0 ? (
            <MetadataListItem label="Matched required">
              {skillNames(match.matchedRequiredSkills)}
            </MetadataListItem>
          ) : null}
          {match.relatedSkills.length > 0 ? (
            <MetadataListItem label="Related verified">
              {skillNames(match.relatedSkills)}
            </MetadataListItem>
          ) : null}
          {match.missingRequiredSkills.length > 0 ? (
            <MetadataListItem label="Missing required">
              {skillNames(match.missingRequiredSkills)}
            </MetadataListItem>
          ) : null}
          {match.sourceUrl ? (
            <MetadataListItem label="Source">
              <Link
                href={match.sourceUrl}
                isExternalLink
                data-testid={`${testId}-source`}
              >
                {match.sourceUrl}
              </Link>
            </MetadataListItem>
          ) : null}
        </MetadataList>

        {match.explanationLines.length > 0 ? (
          <VStack gap={1} data-testid={`${testId}-explanations`}>
            {match.explanationLines.map((line, index) => (
              <Text
                key={`${match.jobId}-exp-${String(index)}`}
                type="supporting"
                as="p"
              >
                {line}
              </Text>
            ))}
          </VStack>
        ) : null}

        <ScoreBreakdown
          components={match.components}
          data-testid={`${testId}-breakdown`}
        />
      </VStack>
    </Card>
  );
}

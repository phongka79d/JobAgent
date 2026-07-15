/**
 * Compact match_jobs result card (Plan 6 §7.9 / Master §15.5).
 * Renders durable match ToolResult projection via public Astryx Card,
 * MetadataList, Link, Token, and ScoreBreakdown Collapsible.
 * Skills use Token (not decorative chips); no raw layout; backend order preserved by caller.
 */

import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Link} from '@astryxdesign/core/Link';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {Token} from '@astryxdesign/core/Token';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import {
  formatDisplayScore,
  type CompactMatchResult,
  type CompactMatchSkillEvidence,
  type CompactMissingRequiredSkill,
} from './matchResult';
import {ScoreBreakdown} from './ScoreBreakdown';

export type MatchCardProps = {
  data: CompactMatchResult;
};

function SkillTokens({
  skills,
  emptyLabel,
  color,
  testId,
}: {
  skills: readonly CompactMatchSkillEvidence[] | readonly CompactMissingRequiredSkill[];
  emptyLabel: string;
  color: 'green' | 'blue' | 'red' | 'gray';
  testId: string;
}) {
  if (skills.length === 0) {
    return (
      <Text type="supporting" color="secondary" as="p" data-testid={testId}>
        {emptyLabel}
      </Text>
    );
  }
  return (
    <HStack gap={1} data-testid={testId}>
      {skills.map((skill) => (
        <Token
          key={skill.jobSkillKey}
          label={skill.jobSkillDisplayName}
          size="sm"
          color={color}
        />
      ))}
    </HStack>
  );
}

export function MatchCard({data}: MatchCardProps) {
  const heading =
    data.title?.trim() ||
    data.company?.trim() ||
    'Match result';

  return (
    <Card
      padding={3}
      variant="default"
      maxWidth="100%"
      data-testid="jobagent-match-card"
      data-job-id={data.jobId}
      data-final-score={String(data.finalScore)}
    >
      <VStack gap={2} width="100%">
        <Heading level={4}>{heading}</Heading>
        <MetadataList
          columns="single"
          label={{position: 'start'}}
          data-testid="jobagent-match-metadata"
        >
          <MetadataListItem label="Job ID">{data.jobId}</MetadataListItem>
          {data.company ? (
            <MetadataListItem label="Company">{data.company}</MetadataListItem>
          ) : null}
          {data.title ? (
            <MetadataListItem label="Title">{data.title}</MetadataListItem>
          ) : null}
          {data.location ? (
            <MetadataListItem label="Location">{data.location}</MetadataListItem>
          ) : null}
          <MetadataListItem label="Work mode">{data.workMode}</MetadataListItem>
          <MetadataListItem label="Final score">
            <Text
              type="body"
              as="span"
              data-testid="jobagent-match-final-score"
            >
              {formatDisplayScore(data.finalScore)}
            </Text>
          </MetadataListItem>
          {data.sourceUrl ? (
            <MetadataListItem label="Source">
              <Link href={data.sourceUrl} isExternalLink hasUnderline>
                {data.sourceUrl}
              </Link>
            </MetadataListItem>
          ) : null}
        </MetadataList>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            Matched required skills
          </Text>
          <SkillTokens
            skills={data.matchedRequiredSkills}
            emptyLabel="None"
            color="green"
            testId="jobagent-match-matched-required"
          />
        </VStack>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            Seed-related skills
          </Text>
          <SkillTokens
            skills={data.relatedSkills}
            emptyLabel="None"
            color="blue"
            testId="jobagent-match-related-skills"
          />
        </VStack>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            Missing required skills
          </Text>
          <SkillTokens
            skills={data.missingRequiredSkills}
            emptyLabel="None"
            color="red"
            testId="jobagent-match-missing-required"
          />
        </VStack>

        {data.summary ? (
          <Text type="supporting" color="secondary" as="p">
            {data.summary}
          </Text>
        ) : null}

        <ScoreBreakdown data={data} />
      </VStack>
    </Card>
  );
}

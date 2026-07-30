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
import {JOB_COPY, matchDisplayLabel} from './copy';

export type MatchCardProps = {
  data: CompactMatchResult;
  /** Saved-JD detail already owns identity metadata in its header. */
  showJobMetadata?: boolean;
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
    <HStack
      gap={1}
      wrap="wrap"
      width="100%"
      className="jobagent-match-skill-tokens"
      data-testid={testId}
    >
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

function workModeLabel(mode: CompactMatchResult['workMode']): string {
  return JOB_COPY.workModes[mode];
}

export function MatchCard({data, showJobMetadata = true}: MatchCardProps) {
  const heading = matchDisplayLabel(data);

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
        {showJobMetadata ? <Heading level={4}>{heading}</Heading> : null}
        <HStack
          gap={2}
          wrap="wrap"
          width="100%"
          className="jobagent-match-score-summary"
          data-testid="jobagent-match-score-summary"
        >
          <VStack gap={0} className="jobagent-match-score-primary">
            <Text type="supporting" color="secondary" as="span">
              {JOB_COPY.matchScore}
            </Text>
            <Text
              type="large"
              as="span"
              data-testid="jobagent-match-final-score"
            >
              {formatDisplayScore(data.finalScore)}
            </Text>
          </VStack>
          <Text type="supporting" color="secondary" as="span">
            {JOB_COPY.scoreExplanation}
          </Text>
        </HStack>
        {showJobMetadata ? (
          <MetadataList
            columns="single"
            label={{position: 'start'}}
            data-testid="jobagent-match-metadata"
          >
            {data.company ? (
              <MetadataListItem label={JOB_COPY.company}>{data.company}</MetadataListItem>
            ) : null}
            {data.title ? (
              <MetadataListItem label={JOB_COPY.role}>{data.title}</MetadataListItem>
            ) : null}
            {data.location ? (
              <MetadataListItem label={JOB_COPY.location}>{data.location}</MetadataListItem>
            ) : null}
            <MetadataListItem label={JOB_COPY.workMode}>
              {workModeLabel(data.workMode)}
            </MetadataListItem>
            {data.sourceUrl ? (
              <MetadataListItem label={JOB_COPY.source}>
                <Link href={data.sourceUrl} isExternalLink hasUnderline>
                  {data.sourceUrl}
                </Link>
              </MetadataListItem>
            ) : null}
          </MetadataList>
        ) : null}

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            {JOB_COPY.matchedSkills}
          </Text>
          <SkillTokens
            skills={data.matchedRequiredSkills}
            emptyLabel={JOB_COPY.noSkills}
            color="green"
            testId="jobagent-match-matched-required"
          />
        </VStack>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            {JOB_COPY.relatedSkills}
          </Text>
          <SkillTokens
            skills={data.relatedSkills}
            emptyLabel={JOB_COPY.noSkills}
            color="blue"
            testId="jobagent-match-related-skills"
          />
        </VStack>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            {JOB_COPY.missingSkills}
          </Text>
          <SkillTokens
            skills={data.missingRequiredSkills}
            emptyLabel={JOB_COPY.noSkills}
            color="red"
            testId="jobagent-match-missing-required"
          />
        </VStack>

        <ScoreBreakdown data={data} />
      </VStack>
    </Card>
  );
}

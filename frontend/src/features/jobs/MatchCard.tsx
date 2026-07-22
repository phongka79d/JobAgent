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
  formatQualityMultiplier,
  type CompactMatchResult,
  type CompactMatchSkillEvidence,
  type CompactMissingRequiredSkill,
} from './matchResult';
import {ScoreBreakdown} from './ScoreBreakdown';

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
  switch (mode) {
    case 'remote':
      return 'Từ xa';
    case 'hybrid':
      return 'Kết hợp';
    case 'onsite':
      return 'Tại văn phòng';
    case 'unknown':
    default:
      return 'Chưa xác định';
  }
}

export function MatchCard({data, showJobMetadata = true}: MatchCardProps) {
  const heading =
    data.title?.trim() ||
    data.company?.trim() ||
    'Kết quả đối chiếu';

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
              Điểm phù hợp
            </Text>
            <Text
              type="large"
              as="span"
              data-testid="jobagent-match-final-score"
            >
              {formatDisplayScore(data.finalScore)}
            </Text>
          </VStack>
          <VStack gap={0} className="jobagent-match-score-metric">
            <Text type="supporting" color="secondary" as="span">
              Độ tương đồng
            </Text>
            <Text type="label" as="span">
              {formatDisplayScore(data.components.semanticSimilarity)}
            </Text>
          </VStack>
          <VStack gap={0} className="jobagent-match-score-metric">
            <Text type="supporting" color="secondary" as="span">
              Độ phủ kỹ năng
            </Text>
            <Text type="label" as="span">
              {data.components.skillScore === null
                ? 'Chưa có'
                : formatDisplayScore(data.components.skillScore)}
            </Text>
          </VStack>
          <VStack gap={0} className="jobagent-match-score-metric">
            <Text type="supporting" color="secondary" as="span">
              Hệ số chất lượng
            </Text>
            <Text type="label" as="span">
              {formatQualityMultiplier(data.qualityMultiplier)}
            </Text>
          </VStack>
        </HStack>
        {showJobMetadata ? (
          <MetadataList
            columns="single"
            label={{position: 'start'}}
            data-testid="jobagent-match-metadata"
          >
            <MetadataListItem label="Mã JD">{data.jobId}</MetadataListItem>
            {data.company ? (
              <MetadataListItem label="Công ty">{data.company}</MetadataListItem>
            ) : null}
            {data.title ? (
              <MetadataListItem label="Vị trí">{data.title}</MetadataListItem>
            ) : null}
            {data.location ? (
              <MetadataListItem label="Địa điểm">{data.location}</MetadataListItem>
            ) : null}
            <MetadataListItem label="Hình thức làm việc">
              {workModeLabel(data.workMode)}
            </MetadataListItem>
            {data.sourceUrl ? (
              <MetadataListItem label="Nguồn">
                <Link href={data.sourceUrl} isExternalLink hasUnderline>
                  {data.sourceUrl}
                </Link>
              </MetadataListItem>
            ) : null}
          </MetadataList>
        ) : null}

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            Kỹ năng đã khớp
          </Text>
          <SkillTokens
            skills={data.matchedRequiredSkills}
            emptyLabel="Không có"
            color="green"
            testId="jobagent-match-matched-required"
          />
        </VStack>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            Kỹ năng liên quan
          </Text>
          <SkillTokens
            skills={data.relatedSkills}
            emptyLabel="Không có"
            color="blue"
            testId="jobagent-match-related-skills"
          />
        </VStack>

        <VStack gap={1} width="100%">
          <Text type="label" as="p">
            Kỹ năng còn thiếu
          </Text>
          <SkillTokens
            skills={data.missingRequiredSkills}
            emptyLabel="Không có"
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

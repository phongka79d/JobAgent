import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Text} from '@astryxdesign/core/Text';
import {Token} from '@astryxdesign/core/Token';
import {VStack} from '@astryxdesign/core/VStack';

import {JOB_COPY} from './copy';
import {formatDisplayScore, type CompactMatchResult} from './matchResult';

export type ScoreBreakdownProps = {data: CompactMatchResult};

export function ScoreBreakdown({data}: ScoreBreakdownProps) {
  return (
    <Collapsible trigger={JOB_COPY.whyThisScore} defaultIsOpen={false} data-testid="jobagent-match-score-breakdown">
      <VStack gap={2} width="100%">
        <Text type="supporting" color="secondary" as="p">
          {JOB_COPY.overallMatch(formatDisplayScore(data.finalScore))}
        </Text>
        <Text type="label" as="p">{JOB_COPY.matchedSkills}</Text>
        {data.matchedRequiredSkills.map((skill) => (
          <Token key={skill.jobSkillKey} label={skill.jobSkillDisplayName} size="sm" color="green" />
        ))}
        <Text type="label" as="p">{JOB_COPY.relatedSkills}</Text>
        {data.relatedSkills.map((skill) => (
          <Token key={skill.jobSkillKey} label={skill.jobSkillDisplayName} size="sm" color="blue" />
        ))}
        <Text type="label" as="p">{JOB_COPY.missingSkills}</Text>
        {data.missingRequiredSkills.map((skill) => (
          <Token key={skill.jobSkillKey} label={skill.jobSkillDisplayName} size="sm" color="red" />
        ))}
        {data.components.experienceScore === null ? (
          <Text type="supporting" color="secondary" as="p">{JOB_COPY.notEnoughExperience}</Text>
        ) : null}
        {data.qualityMultiplier < 1 ? (
          <Text type="supporting" color="secondary" as="p">
            {JOB_COPY.incompleteConfidence}
          </Text>
        ) : null}
      </VStack>
    </Collapsible>
  );
}

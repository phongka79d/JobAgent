/**
 * Collapsible match score breakdown (Plan 6 §7.9 / Master §15.5).
 * Public Astryx Collapsible + ProgressBar; display-only rounding.
 * Explicit unavailable component states; effective weights; quality multiplier.
 */

import {Collapsible} from '@astryxdesign/core/Collapsible';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {ProgressBar} from '@astryxdesign/core/ProgressBar';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {
  MATCH_COMPONENT_LABELS,
  componentScoreForKey,
  formatComponentProgressValue,
  formatDisplayWeight,
  formatQualityMultiplier,
  type CompactMatchResult,
  type MatchComponentKey,
} from './matchResult';

/** Stable component order for breakdown rows (display only; not score order). */
const COMPONENT_ROW_ORDER: readonly MatchComponentKey[] = [
  'semantic_similarity',
  'skill_score',
  'seniority_score',
  'experience_score',
  'location_score',
  'work_mode_score',
] as const;

export type ScoreBreakdownProps = {
  data: CompactMatchResult;
};

function weightForKey(
  data: CompactMatchResult,
  key: MatchComponentKey,
): number | null {
  for (const entry of data.effectiveWeights) {
    if (entry.key === key) {
      return entry.weight;
    }
  }
  return null;
}

function ComponentRow({
  data,
  componentKey,
}: {
  data: CompactMatchResult;
  componentKey: MatchComponentKey;
}) {
  const label = MATCH_COMPONENT_LABELS[componentKey];
  const score = componentScoreForKey(data.components, componentKey);
  const weight = weightForKey(data, componentKey);
  const testId = `jobagent-match-component-${componentKey}`;

  if (score === null) {
    return (
      <VStack gap={1} width="100%" data-testid={testId} data-available="false">
        <Text type="label" as="p">
          {label}
        </Text>
        <Text type="supporting" color="secondary" as="p">
          Unavailable
        </Text>
        <Text type="supporting" color="secondary" as="p">
          Effective weight: n/a
        </Text>
      </VStack>
    );
  }

  const progressValue = formatComponentProgressValue(score);
  return (
    <VStack gap={1} width="100%" data-testid={testId} data-available="true">
      <ProgressBar
        label={label}
        value={progressValue}
        max={100}
        hasValueLabel
        formatValueLabel={(value) => `${Number(value).toFixed(1)}%`}
        variant="accent"
      />
      <Text type="supporting" color="secondary" as="p">
        Effective weight:{' '}
        {weight === null ? 'n/a' : formatDisplayWeight(weight)}
      </Text>
    </VStack>
  );
}

export function ScoreBreakdown({data}: ScoreBreakdownProps) {
  return (
    <Collapsible
      trigger="Score breakdown"
      defaultIsOpen={false}
      data-testid="jobagent-match-score-breakdown"
    >
      <VStack gap={2} width="100%">
        <MetadataList
          columns="single"
          label={{position: 'start'}}
          data-testid="jobagent-match-quality-meta"
        >
          <MetadataListItem label="Quality multiplier">
            {formatQualityMultiplier(data.qualityMultiplier)}
          </MetadataListItem>
        </MetadataList>
        {COMPONENT_ROW_ORDER.map((key) => (
          <ComponentRow key={key} data={data} componentKey={key} />
        ))}
      </VStack>
    </Collapsible>
  );
}

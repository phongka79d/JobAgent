/**
 * Collapsible component / effective-weight breakdown for a match result.
 * Documented Astryx Collapsible + ProgressBar + MetadataList only.
 */

import { Collapsible } from "@astryxdesign/core/Collapsible";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import {
  formatComponentLabel,
  formatMatchScore,
  type MatchComponentEntry,
} from "../contracts";

export interface ScoreBreakdownProps {
  readonly components: readonly MatchComponentEntry[];
  readonly "data-testid"?: string;
}

function weightLabel(weight: number | null): string {
  if (weight === null || !Number.isFinite(weight)) {
    return "—";
  }
  return formatMatchScore(weight);
}

/**
 * Expandable inventory of component values and effective weights.
 * Unavailable components are listed without progress bars.
 */
export function ScoreBreakdown({
  components,
  "data-testid": testId = "score-breakdown",
}: ScoreBreakdownProps) {
  return (
    <Collapsible
      trigger="Score breakdown"
      defaultIsOpen={false}
      data-testid={testId}
    >
      <VStack gap={3} data-testid={`${testId}-body`}>
        <Text type="supporting" as="p">
          Component values and effective weights after renormalization.
        </Text>
        {components.map((entry) => {
          const label = formatComponentLabel(entry.name);
          if (!entry.available || entry.value === null) {
            return (
              <MetadataList
                key={entry.name}
                columns="single"
                label={{ position: "start" }}
                data-testid={`${testId}-unavailable-${entry.name}`}
              >
                <MetadataListItem label={label}>Unavailable</MetadataListItem>
              </MetadataList>
            );
          }
          const pct = Math.round(entry.value * 100);
          return (
            <VStack key={entry.name} gap={1} data-testid={`${testId}-row-${entry.name}`}>
              <ProgressBar
                label={label}
                value={pct}
                max={100}
                hasValueLabel
                formatValueLabel={(v) => `${Math.round(v)}%`}
                variant="accent"
                data-testid={`${testId}-progress-${entry.name}`}
              />
              <MetadataList
                columns="single"
                label={{ position: "start" }}
              >
                <MetadataListItem label="Effective weight">
                  {weightLabel(entry.effectiveWeight)}
                </MetadataListItem>
              </MetadataList>
            </VStack>
          );
        })}
      </VStack>
    </Collapsible>
  );
}

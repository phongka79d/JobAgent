import {HStack} from '@astryxdesign/core/HStack';
import {Skeleton} from '@astryxdesign/core/Skeleton';
import {VStack} from '@astryxdesign/core/VStack';

export type ObservabilityListSkeletonProps = {
  rows: number;
  testId: string;
};

export function ObservabilityListSkeleton({
  rows,
  testId,
}: ObservabilityListSkeletonProps) {
  return (
    <VStack gap={2} data-testid={testId}>
      {Array.from({length: rows}, (_, index) => (
        <HStack key={index} gap={2} vAlign="center">
          <Skeleton
            width="70%"
            height="var(--spacing-3)"
            index={index * 2}
          />
          <Skeleton
            width="25%"
            height="var(--spacing-3)"
            index={index * 2 + 1}
          />
        </HStack>
      ))}
    </VStack>
  );
}

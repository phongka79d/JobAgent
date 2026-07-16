import {HStack} from '@astryxdesign/core/HStack';
import {IconButton} from '@astryxdesign/core/IconButton';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

export type ObservabilityPanelHeaderProps = {
  eyebrow: string;
  title: string;
  onRefresh: () => void;
  isRefreshing: boolean;
  refreshTestId: string;
};

export function ObservabilityPanelHeader({
  eyebrow,
  title,
  onRefresh,
  isRefreshing,
  refreshTestId,
}: ObservabilityPanelHeaderProps) {
  return (
    <HStack hAlign="between" vAlign="center">
      <VStack gap={0.5}>
        <Text type="label" color="secondary" display="block">
          {eyebrow}
        </Text>
        <Text type="large" display="block">
          {title}
        </Text>
      </VStack>
      <IconButton
        label={`Refresh ${title}`}
        tooltip={`Refresh ${title}`}
        icon={<span aria-hidden="true">{'\u21bb'}</span>}
        variant="ghost"
        size="sm"
        isLoading={isRefreshing}
        onClick={onRefresh}
        data-testid={refreshTestId}
      />
    </HStack>
  );
}

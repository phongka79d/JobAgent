import {AppShell} from '@astryxdesign/core/AppShell';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

/**
 * Minimal Phase 1 foundation shell. No chat, sidebar, approval, or match UI.
 * Plan 3 extends this frame with production regions.
 */
export function App() {
  return (
    <AppShell contentPadding={4} height="fill" variant="surface">
      <VStack gap={2}>
        <Heading level={1}>JobAgent</Heading>
        <Text type="supporting" color="secondary" as="p">
          Astryx-neutral application foundation
        </Text>
      </VStack>
    </AppShell>
  );
}

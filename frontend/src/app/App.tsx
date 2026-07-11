import { Theme } from "@astryxdesign/core";
import { AppShell } from "@astryxdesign/core/AppShell";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

/**
 * Neutral Phase 1 shell only.
 * No chat, upload, profile, job, matching, CRUD, or health UI.
 */
export function App() {
  return (
    <Theme theme={neutralTheme} mode="system">
      <AppShell contentPadding={6} height="fill" variant="surface">
        <VStack gap={4}>
          <Heading level={1}>JobAgent</Heading>
          <Text type="body" as="p">
            Local frontend scaffold is ready. Product workflows are intentionally
            disabled in this phase.
          </Text>
        </VStack>
      </AppShell>
    </Theme>
  );
}

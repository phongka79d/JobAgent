import {AppShell} from '@astryxdesign/core/AppShell';

import {ChatPage} from '../features/chat/ChatPage';

/**
 * Plan 3 base conversation shell: AppShell → ChatPage (ChatLayout + composer).
 * No sidebar, approval cards, profile, or domain-tool UI in this phase.
 */
export function App() {
  return (
    <AppShell contentPadding={0} height="fill" variant="surface">
      <ChatPage />
    </AppShell>
  );
}

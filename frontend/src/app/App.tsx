import { Theme } from "@astryxdesign/core";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

import { ChatShell } from "../features/chat/components/ChatShell";

/**
 * Plan 4 Batch05 shell: single AppShell with responsive profile sideNav + chat.
 * Frontend talks only to FastAPI (profile reads, CV upload, chat turns).
 * No direct store/provider access.
 */
export function App() {
  return (
    <Theme theme={neutralTheme} mode="system">
      <ChatShell wrapTheme={false} enableProfileSidebar />
    </Theme>
  );
}

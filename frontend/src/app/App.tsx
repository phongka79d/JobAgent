import { Theme } from "@astryxdesign/core";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

import { ChatShell } from "../features/chat/components/ChatShell";

/**
 * Plan 3 first screen: base Astryx chat experience (history, stream, tools, approval).
 * No upload/profile/job/match UI or direct provider/store access.
 */
export function App() {
  return (
    <Theme theme={neutralTheme} mode="system">
      <ChatShell wrapTheme={false} />
    </Theme>
  );
}

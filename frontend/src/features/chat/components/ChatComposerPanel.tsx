/**
 * Chat composer panel: documented ChatComposer with send-disabled and status.
 */

import { ChatComposer } from "@astryxdesign/core/Chat";

export interface ChatComposerPanelProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly onStop?: () => void;
  /** Conflicting send disabled while active or awaiting approval. */
  readonly isDisabled: boolean;
  /** Show stop while a generation stream is active (not approval wait). */
  readonly isStopShown?: boolean;
  readonly placeholder?: string;
  readonly status?: { type: "error" | "warning"; message?: string };
  readonly "data-testid"?: string;
}

export function ChatComposerPanel({
  value,
  onChange,
  onSubmit,
  onStop,
  isDisabled,
  isStopShown = false,
  placeholder = "Message JobAgent…",
  status,
  "data-testid": testId = "chat-composer",
}: ChatComposerPanelProps) {
  return (
    <ChatComposer
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      onStop={onStop}
      isStopShown={isStopShown}
      isDisabled={isDisabled}
      placeholder={placeholder}
      status={status}
      statusPosition="top"
      density="balanced"
      data-testid={testId}
    />
  );
}

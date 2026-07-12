/**
 * Approval / resume controls for interrupted agent runs.
 * Profile drafts use ProfileApprovalCard; other interrupts keep generic Approve/Correct.
 */

import { useState } from "react";

import { Button } from "@astryxdesign/core/Button";
import { ButtonGroup } from "@astryxdesign/core/ButtonGroup";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { VStack } from "@astryxdesign/core/VStack";

import { isProfileDraftApproval, type ApprovalState } from "../reducer";
import { ProfileApprovalCard } from "./ProfileApprovalCard";

export interface ChatApprovalProps {
  readonly approval: ApprovalState;
  /** True while a resume stream is already in flight or send is otherwise blocked. */
  readonly isDisabled: boolean;
  readonly onApprove: () => void;
  /** Invoked only with nonblank correction text (generic path). */
  readonly onCorrect: (correctionText: string) => void;
  /**
   * Profile path: enter correction mode and focus main composer.
   * When omitted, falls back to generic inline correction.
   */
  readonly onRequestChanges?: () => void;
  readonly "data-testid"?: string;
}

/**
 * Surfaces a friendly approval summary and actions.
 * Never renders internal-only IDs, raw payloads, paths, or tool arguments.
 */
export function ChatApproval({
  approval,
  isDisabled,
  onApprove,
  onCorrect,
  onRequestChanges,
  "data-testid": testId = "chat-approval",
}: ChatApprovalProps) {
  const [correctionText, setCorrectionText] = useState("");
  const [showEmptyError, setShowEmptyError] = useState(false);

  if (isProfileDraftApproval(approval) && onRequestChanges) {
    return (
      <VStack gap={2} data-testid={testId}>
        <ProfileApprovalCard
          approval={approval}
          isDisabled={isDisabled}
          onSaveProfile={onApprove}
          onRequestChanges={onRequestChanges}
        />
      </VStack>
    );
  }

  const trimmedCorrection = correctionText.trim();
  const hasCorrection = trimmedCorrection.length > 0;
  const correctDisabled = isDisabled || !hasCorrection;

  const handleCorrect = () => {
    if (isDisabled) {
      return;
    }
    if (!hasCorrection) {
      setShowEmptyError(true);
      return;
    }
    setShowEmptyError(false);
    onCorrect(trimmedCorrection);
  };

  return (
    <VStack gap={3} data-testid={testId}>
      <Text type="body" as="p" data-testid="chat-approval-summary">
        {approval.summary}
      </Text>
      <TextArea
        label="Correction"
        description="Describe what should change before the agent continues."
        value={correctionText}
        onChange={(value) => {
          setCorrectionText(value);
          if (value.trim().length > 0) {
            setShowEmptyError(false);
          }
        }}
        isDisabled={isDisabled}
        isRequired
        rows={3}
        width="100%"
        placeholder="Enter a correction for the agent…"
        status={
          showEmptyError
            ? {
                type: "error",
                message: "Enter a nonblank correction before continuing.",
              }
            : undefined
        }
        data-testid="chat-approval-correction"
      />
      <ButtonGroup label="Approval actions" size="md" isDisabled={isDisabled}>
        <Button
          label="Approve"
          variant="primary"
          isDisabled={isDisabled}
          onClick={onApprove}
          data-testid="chat-approval-approve"
        />
        <Button
          label="Correct"
          variant="secondary"
          isDisabled={correctDisabled}
          onClick={handleCorrect}
          data-testid="chat-approval-correct"
        />
      </ButtonGroup>
    </VStack>
  );
}

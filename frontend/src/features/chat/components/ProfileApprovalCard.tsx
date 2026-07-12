/**
 * Profile-draft approval card: sanitized summary + Save Profile / Request Changes.
 * No raw CV, contact PII, internal IDs, paths, or tool arguments.
 */

import { Button } from "@astryxdesign/core/Button";
import { ButtonGroup } from "@astryxdesign/core/ButtonGroup";
import { Card } from "@astryxdesign/core/Card";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import type { ApprovalState } from "../reducer";

export interface ProfileApprovalCardProps {
  readonly approval: ApprovalState;
  /** True while a resume is in flight, correction mode is open, or phase left approval. */
  readonly isDisabled: boolean;
  readonly onSaveProfile: () => void;
  /** Enters correction mode and focuses the main composer (does not resume yet). */
  readonly onRequestChanges: () => void;
  readonly "data-testid"?: string;
}

function formatCount(value: number | null): string | null {
  if (value === null || value < 0) {
    return null;
  }
  return String(value);
}

/**
 * Renders only typed display-safe profile/preference fields and exact source actions.
 */
export function ProfileApprovalCard({
  approval,
  isDisabled,
  onSaveProfile,
  onRequestChanges,
  "data-testid": testId = "profile-approval-card",
}: ProfileApprovalCardProps) {
  const title = approval.currentTitle?.trim() || null;
  const skills =
    approval.skillNames.length > 0 ? approval.skillNames.join(", ") : null;
  const roles =
    approval.targetRolesPreview.length > 0
      ? approval.targetRolesPreview.join(", ")
      : null;
  const experience = formatCount(approval.experienceCount);
  const education = formatCount(approval.educationCount);
  const prefs =
    approval.hasPreferenceChanges === null
      ? null
      : approval.hasPreferenceChanges
        ? "Yes"
        : "No";

  return (
    <Card padding={4} data-testid={testId} data-instance-key={approval.instanceKey}>
      <VStack gap={3}>
        <Text type="body" as="p" data-testid="profile-approval-summary">
          {approval.summary}
        </Text>

        <MetadataList
          columns="single"
          label={{ position: "start" }}
          data-testid="profile-approval-metadata"
        >
          {title ? (
            <MetadataListItem label="Title">{title}</MetadataListItem>
          ) : null}
          {skills ? (
            <MetadataListItem label="Skills">{skills}</MetadataListItem>
          ) : null}
          {experience !== null ? (
            <MetadataListItem label="Experience items">
              {experience}
            </MetadataListItem>
          ) : null}
          {education !== null ? (
            <MetadataListItem label="Education items">
              {education}
            </MetadataListItem>
          ) : null}
          {prefs !== null ? (
            <MetadataListItem label="Preference changes">{prefs}</MetadataListItem>
          ) : null}
          {roles ? (
            <MetadataListItem label="Target roles">{roles}</MetadataListItem>
          ) : null}
        </MetadataList>

        <ButtonGroup
          label="Profile approval actions"
          size="md"
          isDisabled={isDisabled}
        >
          <Button
            label="Save Profile"
            variant="primary"
            isDisabled={isDisabled}
            onClick={onSaveProfile}
            data-testid="profile-approval-save"
          />
          <Button
            label="Request Changes"
            variant="secondary"
            isDisabled={isDisabled}
            onClick={onRequestChanges}
            data-testid="profile-approval-request-changes"
          />
        </ButtonGroup>
      </VStack>
    </Card>
  );
}

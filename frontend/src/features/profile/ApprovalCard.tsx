/**
 * In-chat profile approval card (Master §10.3 / Plan 4 §7.6–7.8).
 * Compact summary + exactly Save Profile / Request Changes via public Astryx
 * Card, ButtonGroup, and Button. No raw CV content, no second store.
 */

import {Button} from '@astryxdesign/core/Button';
import {ButtonGroup} from '@astryxdesign/core/ButtonGroup';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {JsonObject, JsonValue} from '../chat/types';

/** Exact resume actions for profile_commit interrupts. */
export const SAVE_PROFILE_ACTION = 'save_profile' as const;
export const REQUEST_CHANGES_ACTION = 'request_changes' as const;

export type ProfileApprovalAction =
  | typeof SAVE_PROFILE_ACTION
  | typeof REQUEST_CHANGES_ACTION;

export const PROFILE_COMMIT_KIND = 'profile_commit';

export const SAVE_PROFILE_LABEL = 'Save Profile';
export const REQUEST_CHANGES_LABEL = 'Request Changes';

export type ApprovalCardProps = {
  /** Compact card projection from approval_required / pending_approval. */
  card: JsonObject;
  allowedActions: readonly string[];
  /** True after the first accepted click or while resume is in flight. */
  isDisabled: boolean;
  onAction: (action: ProfileApprovalAction) => void;
  /** Optional run id for test selectors. */
  runId?: string;
};

function asNonEmptyString(value: JsonValue | undefined): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function asStringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
}

/**
 * Build safe, compact summary lines from the interrupt card projection.
 * Never surfaces raw CV text, storage paths, or full JSON dumps.
 */
export function summarizeApprovalCard(card: JsonObject): {
  title: string;
  lines: string[];
} {
  const currentTitle =
    asNonEmptyString(card.current_title) ??
    asNonEmptyString(card.title) ??
    asNonEmptyString(card.headline);
  const summary = asNonEmptyString(card.summary);

  // Nested profile/preferences objects when present (compact only).
  const profile =
    card.profile !== null &&
    typeof card.profile === 'object' &&
    !Array.isArray(card.profile)
      ? (card.profile as JsonObject)
      : null;
  const preferences =
    card.preferences !== null &&
    typeof card.preferences === 'object' &&
    !Array.isArray(card.preferences)
      ? (card.preferences as JsonObject)
      : null;

  const nestedTitle = profile
    ? asNonEmptyString(profile.current_title)
    : null;
  const nestedSummary = profile ? asNonEmptyString(profile.summary) : null;

  const title =
    currentTitle ?? nestedTitle ?? 'Proposed profile ready for review';

  const lines: string[] = [];
  const body = summary ?? nestedSummary;
  if (body) {
    // Cap length so a mis-shaped payload cannot dump a full CV into chat.
    lines.push(body.length > 280 ? `${body.slice(0, 277)}…` : body);
  }

  const skills = asStringList(card.skills);
  if (skills.length > 0) {
    const preview = skills.slice(0, 6).join(', ');
    lines.push(
      skills.length > 6
        ? `Skills: ${preview} (+${skills.length - 6} more)`
        : `Skills: ${preview}`,
    );
  } else if (typeof card.skill_count === 'number' && card.skill_count > 0) {
    lines.push(`Skills: ${card.skill_count}`);
  }

  const roles = preferences
    ? asStringList(preferences.target_roles)
    : asStringList(card.target_roles);
  if (roles.length > 0) {
    lines.push(`Target roles: ${roles.slice(0, 4).join(', ')}`);
  }

  const locations = preferences
    ? asStringList(preferences.preferred_locations)
    : asStringList(card.preferred_locations);
  if (locations.length > 0) {
    lines.push(`Locations: ${locations.slice(0, 4).join(', ')}`);
  }

  if (lines.length === 0) {
    lines.push(
      'Review the proposed profile and preferences, then save or request changes.',
    );
  }

  return {title, lines};
}

export function isProfileCommitApproval(
  kind: string | null | undefined,
  allowedActions: readonly string[] | null | undefined,
): boolean {
  if (kind !== PROFILE_COMMIT_KIND) {
    return false;
  }
  if (!allowedActions || allowedActions.length === 0) {
    return false;
  }
  return (
    allowedActions.includes(SAVE_PROFILE_ACTION) &&
    allowedActions.includes(REQUEST_CHANGES_ACTION)
  );
}

/**
 * Parse durable pending_approval / SSE payload into card + actions.
 * Returns null when not a profile_commit interrupt.
 */
export function parseProfileCommitProjection(
  pending: JsonObject | null | undefined,
): {
  kind: string;
  allowedActions: string[];
  card: JsonObject;
  draftId: string | null;
} | null {
  if (!pending || typeof pending !== 'object') {
    return null;
  }
  const kind = asNonEmptyString(pending.kind);
  if (kind !== PROFILE_COMMIT_KIND) {
    return null;
  }
  const allowedRaw = pending.allowed_actions;
  const allowedActions = Array.isArray(allowedRaw)
    ? allowedRaw.filter((a): a is string => typeof a === 'string' && a.trim() !== '')
    : [];
  if (!isProfileCommitApproval(kind, allowedActions)) {
    return null;
  }
  const card =
    pending.card !== null &&
    typeof pending.card === 'object' &&
    !Array.isArray(pending.card)
      ? (pending.card as JsonObject)
      : {};
  const draftId =
    pending.draft_id === 'current' || asNonEmptyString(pending.draft_id) === 'current'
      ? 'current'
      : asNonEmptyString(pending.draft_id);
  return {kind, allowedActions, card, draftId};
}

export function ApprovalCard({
  card,
  allowedActions,
  isDisabled,
  onAction,
  runId,
}: ApprovalCardProps) {
  const {title, lines} = summarizeApprovalCard(card);
  const canSave = allowedActions.includes(SAVE_PROFILE_ACTION);
  const canRequest = allowedActions.includes(REQUEST_CHANGES_ACTION);

  return (
    <Card
      padding={3}
      variant="muted"
      maxWidth="100%"
      data-testid="jobagent-approval-card"
      data-run-id={runId}
    >
      <VStack gap={2} width="100%">
        <Heading level={4}>{title}</Heading>
        {lines.map((line, index) => (
          <Text key={`${index}:${line.slice(0, 24)}`} type="supporting" as="p">
            {line}
          </Text>
        ))}
        <ButtonGroup
          label="Profile approval actions"
          size="sm"
          orientation="horizontal"
          isDisabled={isDisabled}
          data-testid="jobagent-approval-actions"
        >
          {canSave ? (
            <Button
              label={SAVE_PROFILE_LABEL}
              variant="primary"
              size="sm"
              isDisabled={isDisabled}
              onClick={() => {
                if (!isDisabled) {
                  onAction(SAVE_PROFILE_ACTION);
                }
              }}
              data-testid="jobagent-approval-save"
            />
          ) : null}
          {canRequest ? (
            <Button
              label={REQUEST_CHANGES_LABEL}
              variant="secondary"
              size="sm"
              isDisabled={isDisabled}
              onClick={() => {
                if (!isDisabled) {
                  onAction(REQUEST_CHANGES_ACTION);
                }
              }}
              data-testid="jobagent-approval-request-changes"
            />
          ) : null}
        </ButtonGroup>
      </VStack>
    </Card>
  );
}

/**
 * Compact pasted-JD save confirmation card (Plan 12 / Master §15.7).
 * Pinned Astryx Card, MetadataList, Badge, ButtonGroup, Button.
 * Presentation only — resume/lock owned by ChatPage.
 */

import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {ButtonGroup} from '@astryxdesign/core/ButtonGroup';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import {
  CANCEL_SAVE_JOB_ACTION,
  CANCEL_SAVE_JOB_LABEL,
  JD_CONFIRMATION_HEADING,
  JD_CONFIRMATION_SENTENCE,
  SAVE_JOB_ACTION,
  SAVE_JOB_LABEL,
  type JobSaveConfirmationAction,
  type JobSaveConfirmationCardData,
} from '../jobSaveConfirmation';

export type JobSaveConfirmationCardProps = {
  card: JobSaveConfirmationCardData;
  allowedActions: readonly string[];
  /** True after the first accepted click or while resume is in flight. */
  isDisabled: boolean;
  onAction: (action: JobSaveConfirmationAction) => void;
  /** Optional run id for test selectors. */
  runId?: string;
};

export function JobSaveConfirmationCard({
  card,
  allowedActions,
  isDisabled,
  onAction,
  runId,
}: JobSaveConfirmationCardProps) {
  const canSave = allowedActions.includes(SAVE_JOB_ACTION);
  const canCancel = allowedActions.includes(CANCEL_SAVE_JOB_ACTION);
  const {preview} = card;
  const hasTitle = preview.title !== null;
  const hasCompany = preview.company !== null;
  const skills = preview.skills;
  const hasMeta = hasTitle || hasCompany;

  return (
    <Card
      padding={3}
      variant="muted"
      maxWidth="100%"
      data-testid="jobagent-jd-confirmation-card"
      data-run-id={runId}
    >
      <VStack gap={2} width="100%">
        <Heading level={4}>{JD_CONFIRMATION_HEADING}</Heading>
        {hasMeta ? (
          <MetadataList columns="single" label={{position: 'start'}}>
            {hasTitle ? (
              <MetadataListItem label="Title">{preview.title}</MetadataListItem>
            ) : null}
            {hasCompany ? (
              <MetadataListItem label="Company">
                {preview.company}
              </MetadataListItem>
            ) : null}
            <MetadataListItem label="Length">
              {String(card.textLength)}
            </MetadataListItem>
          </MetadataList>
        ) : (
          <MetadataList columns="single" label={{position: 'start'}}>
            <MetadataListItem label="Length">
              {String(card.textLength)}
            </MetadataListItem>
          </MetadataList>
        )}
        {skills.length > 0 ? (
          <HStack gap={1} wrap="wrap">
            {skills.map((skill) => (
              <Badge key={skill} variant="neutral" label={skill} />
            ))}
          </HStack>
        ) : null}
        <Text type="supporting" as="p">
          {JD_CONFIRMATION_SENTENCE}
        </Text>
        <ButtonGroup
          label="JD save confirmation actions"
          size="sm"
          orientation="horizontal"
          isDisabled={isDisabled}
          data-testid="jobagent-jd-confirmation-actions"
        >
          {canSave ? (
            <Button
              label={SAVE_JOB_LABEL}
              variant="primary"
              size="sm"
              isDisabled={isDisabled}
              onClick={() => {
                if (!isDisabled) {
                  onAction(SAVE_JOB_ACTION);
                }
              }}
              data-testid="jobagent-jd-confirmation-save"
            />
          ) : null}
          {canCancel ? (
            <Button
              label={CANCEL_SAVE_JOB_LABEL}
              variant="secondary"
              size="sm"
              isDisabled={isDisabled}
              onClick={() => {
                if (!isDisabled) {
                  onAction(CANCEL_SAVE_JOB_ACTION);
                }
              }}
              data-testid="jobagent-jd-confirmation-cancel"
            />
          ) : null}
        </ButtonGroup>
      </VStack>
    </Card>
  );
}

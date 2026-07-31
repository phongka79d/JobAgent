import {useState} from 'react';
import {AlertDialog} from '@astryxdesign/core/AlertDialog';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {CvManagerController} from './state';

type ReviewController = Pick<CvManagerController, 'state' | 'startReextract' | 'loadReview' | 'approveReview' | 'discardReview' | 'closeReview'>;

function formatList(values: string[]): string {
  return values.length > 0 ? values.join(', ') : 'None';
}

export function ProfileReextractReview({controller, onApproved, onDiscarded}: {controller: ReviewController; onApproved?: () => void; onDiscarded?: () => void}) {
  const [isDiscardConfirmOpen, setIsDiscardConfirmOpen] = useState(false);
  const state = controller.state.reextract;
  if (!state || state.phase === 'idle') return null;

  const requestDiscard = () => setIsDiscardConfirmOpen(true);
  const confirmDiscard = async () => {
    if (await controller.discardReview()) {
      setIsDiscardConfirmOpen(false);
      onDiscarded?.();
    }
  };

  if (state.phase === 'loading') {
    return <VStack gap={2} aria-live="polite" aria-atomic="true" data-testid="jobagent-profile-reextract-progress">
      <Heading level={3}>Preparing profile review</Heading>
      <Text type="body">{state.stage?.replaceAll('_', ' ') ?? 'Working'}</Text>
    </VStack>;
  }

  if (state.phase === 'error') {
    const retry = state.profileId === null
      ? null
      : state.operation?.can_review
        ? () => controller.loadReview(state.profileId ?? '', state.operation?.review_revision ?? undefined, state.operation?.operation_id)
        : state.operation?.can_retry
          ? () => controller.startReextract(state.profileId ?? '')
          : state.draftAvailable
            ? () => controller.loadReview(state.profileId ?? '')
            : !state.operation
              ? () => controller.startReextract(state.profileId ?? '')
              : null;
    return <VStack gap={2} aria-live="assertive" aria-atomic="true" aria-describedby="jobagent-profile-review-error">
      <Banner id="jobagent-profile-review-error" status="error" title="Profile review could not be prepared" description={state.error?.summary} />
      {state.operation?.can_review || state.draftAvailable ? <Text type="supporting">A review exists. Retry loads that review without starting another extraction.</Text> : null}
      <HStack gap={1} wrap="wrap">
        {retry ? <Button label="Retry" variant="primary" onClick={() => void retry()} /> : null}
        <Button label="Close" variant="ghost" onClick={controller.closeReview} />
      </HStack>
    </VStack>;
  }

  const review = state.review;
  if (!review) return null;
  const saveReason = review.can_approve ? undefined : 'Save is unavailable because this server review cannot be approved.';
  const discardReason = review.can_discard ? undefined : 'Discard is unavailable because this server review cannot be discarded.';
  return <VStack gap={3} aria-describedby={state.error ? 'jobagent-profile-review-summary jobagent-profile-review-error' : 'jobagent-profile-review-summary'} data-testid="jobagent-profile-reextract-review">
    <Heading level={3}>Review changes</Heading>
    <Text id="jobagent-profile-review-summary" type="body">Your approved profile stays unchanged until you save this review.</Text>
    {state.error ? <Banner id="jobagent-profile-review-error" status="warning" title="Re-extraction reported a recoverable issue" description={state.error.summary} /> : null}
    {review.changed_fields.length > 0 ? <Collapsible trigger="Changed profile details" defaultIsOpen>
      <VStack gap={1}>
        {review.changed_fields.map((change) => <Text id={`jobagent-profile-review-change-${change.field}`} key={change.field} type="supporting">{change.field.replaceAll('_', ' ')}: {String(change.before ?? 'Not provided')} → {String(change.after ?? 'Not provided')}</Text>)}
      </VStack>
    </Collapsible> : <Text type="supporting">No profile detail changes.</Text>}
    {review.preference_changes.length > 0 ? <Collapsible trigger="Job preference changes" defaultIsOpen>
      <VStack gap={1}>
        {review.preference_changes.map((change) => <Text id={`jobagent-profile-review-preference-${change.field}`} key={change.field} type="supporting">{change.field.replaceAll('_', ' ')}: {formatList(change.before)} -&gt; {formatList(change.after)}</Text>)}
      </VStack>
    </Collapsible> : null}
    <Collapsible trigger="Skill changes" defaultIsOpen>
      <VStack gap={1}>
        <Text type="supporting">Skills added: {review.skills_added.join(', ') || 'None'}</Text>
        <Text type="supporting">Skills removed: {review.skills_removed.join(', ') || 'None'}</Text>
      </VStack>
    </Collapsible>
    {saveReason ? <Text id="jobagent-profile-review-save-reason" type="supporting">{saveReason}</Text> : null}
    {discardReason ? <Text id="jobagent-profile-review-discard-reason" type="supporting">{discardReason}</Text> : null}
    <HStack gap={1} wrap="wrap">
      <Button label="Save review" variant="primary" isDisabled={!review.can_approve} aria-describedby={saveReason ? 'jobagent-profile-review-save-reason' : undefined} onClick={() => void controller.approveReview().then((ok) => { if (ok) onApproved?.(); })} />
      <Button label="Discard review" variant="secondary" isDisabled={!review.can_discard} aria-describedby={discardReason ? 'jobagent-profile-review-discard-reason' : undefined} onClick={requestDiscard} />
      <Button label="Close" variant="ghost" onClick={controller.closeReview} />
    </HStack>
    <AlertDialog isOpen={isDiscardConfirmOpen} onOpenChange={setIsDiscardConfirmOpen} title="Discard this profile review?" description="This keeps your approved profile unchanged and removes this proposed review." actionLabel="Discard review" actionVariant="destructive" onAction={() => void confirmDiscard()} />
  </VStack>;
}

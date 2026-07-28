import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {CvManagerController} from './state';

type ReviewController = Pick<
  CvManagerController,
  'state' | 'startReextract' | 'approveReview' | 'discardReview' | 'closeReview'
>;

export function ProfileReextractReview({controller, onApproved}: {controller: ReviewController; onApproved?: () => void}) {
  const state = controller.state.reextract;
  if (!state || state.phase === 'idle') return null;
  if (state.phase === 'loading') {
    return <VStack gap={2} aria-live="polite" data-testid="jobagent-profile-reextract-progress">
      <Heading level={3}>Preparing profile review</Heading>
      <Text type="body">{state.stage?.replaceAll('_', ' ') ?? 'Working'}</Text>
    </VStack>;
  }
  if (state.phase === 'error') {
    return <VStack gap={2} aria-live="assertive">
      <Banner status="error" title="Profile review could not be prepared" description={state.error?.summary} />
      <HStack gap={1} wrap="wrap">
        {state.profileId ? <Button label="Retry" variant="primary" onClick={() => void controller.startReextract(state.profileId!)} /> : null}
        {state.review?.can_discard ? <Button label="Discard review" variant="secondary" onClick={() => void controller.discardReview()} /> : null}
        <Button label="Close" variant="ghost" onClick={controller.closeReview} />
      </HStack>
    </VStack>;
  }
  const review = state.review;
  if (!review) return null;
  return <VStack gap={3} aria-describedby="jobagent-profile-review-summary" data-testid="jobagent-profile-reextract-review">
    <Heading level={3}>Review changes</Heading>
    <Text id="jobagent-profile-review-summary" type="body">Your approved profile stays unchanged until you save this review.</Text>
    {review.changed_fields.length > 0 ? <VStack gap={1}>
      <Heading level={4}>Changed profile details</Heading>
      {review.changed_fields.map((change) => <Text id={`jobagent-profile-review-change-${change.field}`} key={change.field} type="supporting">{change.field.replaceAll('_', ' ')}: {String(change.before ?? 'Not provided')} → {String(change.after ?? 'Not provided')}</Text>)}
    </VStack> : <Text type="supporting">No profile detail changes.</Text>}
    <VStack gap={1}>
      <Heading level={4}>Skills added</Heading>
      <Text type="supporting">{review.skills_added.join(', ') || 'None'}</Text>
      <Heading level={4}>Skills removed</Heading>
      <Text type="supporting">{review.skills_removed.join(', ') || 'None'}</Text>
    </VStack>
    <HStack gap={1} wrap="wrap">
      <Button label="Save review" variant="primary" isDisabled={!review.can_approve} onClick={() => void controller.approveReview().then((ok) => { if (ok) onApproved?.(); })} />
      <Button label="Discard review" variant="secondary" isDisabled={!review.can_discard} onClick={() => void controller.discardReview()} />
      <Button label="Close" variant="ghost" onClick={controller.closeReview} />
    </HStack>
  </VStack>;
}

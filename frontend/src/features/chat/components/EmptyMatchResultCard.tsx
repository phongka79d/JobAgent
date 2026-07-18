/**
 * Zero-result match_jobs recovery card (Plan 10 Zero-Result Chat UX).
 * Exact Vietnamese heading/CTA; durable source_message_id action only.
 * Success reuses MatchCard; unavailable/error keeps truthful recovery UI.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {MatchCard} from '../../jobs/MatchCard';
import type {CompactMatchResult} from '../../jobs/matchResult';

export const EMPTY_MATCH_HEADING = 'Chưa có kết quả đánh giá';
export const EMPTY_MATCH_CTA = 'Lưu JD & đánh giá lại';

/** One short nontechnical explanation (Master §15.5 / Plan 10). */
export const EMPTY_MATCH_EXPLANATION =
  'JD từ tin nhắn này chưa có đánh giá đã lưu.';

export const EMPTY_MATCH_UNAVAILABLE_HINT =
  'JD có thể đã được lưu nhưng chưa đánh giá được. Thử lại hoặc gửi lại tin nhắn.';

export const EMPTY_MATCH_ERROR_HINT =
  'Không thể lưu và đánh giá lúc này. Thử lại hoặc gửi lại tin nhắn.';

export type EmptyMatchResultCardProps = {
  /** Durable initiating user message id only — never composer/latest inference. */
  sourceMessageId: string;
  isPending: boolean;
  /** Persisted MatchResult after created/reused success. */
  recoveredMatch: CompactMatchResult | null;
  /** Safe instruction when unavailable or transport/error (no success claim). */
  failureHint: string | null;
  onSaveAndEvaluate: (sourceMessageId: string) => void;
};

export function EmptyMatchResultCard({
  sourceMessageId,
  isPending,
  recoveredMatch,
  failureHint,
  onSaveAndEvaluate,
}: EmptyMatchResultCardProps) {
  if (recoveredMatch) {
    return (
      <VStack
        gap={1}
        width="100%"
        data-testid="jobagent-empty-match-recovered"
        data-source-message-id={sourceMessageId}
      >
        <MatchCard data={recoveredMatch} />
      </VStack>
    );
  }

  return (
    <Card
      padding={3}
      variant="default"
      maxWidth="100%"
      data-testid="jobagent-empty-match-card"
      data-source-message-id={sourceMessageId}
    >
      <VStack gap={2} width="100%">
        <Heading level={4}>{EMPTY_MATCH_HEADING}</Heading>
        <Text type="supporting" color="secondary" as="p">
          {EMPTY_MATCH_EXPLANATION}
        </Text>
        <Button
          label={EMPTY_MATCH_CTA}
          variant="primary"
          size="sm"
          isDisabled={isPending}
          isLoading={isPending}
          onClick={() => {
            onSaveAndEvaluate(sourceMessageId);
          }}
          data-testid="jobagent-empty-match-cta"
        />
        {failureHint ? (
          <Banner
            status="warning"
            title="Chưa đánh giá được"
            description={failureHint}
            container="section"
            data-testid="jobagent-empty-match-failure"
          />
        ) : null}
      </VStack>
    </Card>
  );
}

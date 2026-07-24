import {Button} from '@astryxdesign/core/Button';
import {DropdownMenu} from '@astryxdesign/core/DropdownMenu';
import {List, ListItem} from '@astryxdesign/core/List';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  ConversationSummary,
  ProfileListItem,
} from './conversationTypes';

export type ConversationListPanelProps = {
  profileId: string | null;
  profileState: ProfileListItem['state'] | null;
  conversations: readonly ConversationSummary[];
  selectedConversationId: string | null;
  isInteractionLocked: boolean;
  onCreate: (profileId: string) => void;
  onSelect: (conversationId: string) => void;
  onDelete: (conversation: ConversationSummary) => void;
};

function formatActivity(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function ConversationListPanel({
  profileId,
  profileState,
  conversations,
  selectedConversationId,
  isInteractionLocked,
  onCreate,
  onSelect,
  onDelete,
}: ConversationListPanelProps) {
  const isReady = profileId !== null && profileState === 'ready';

  return (
    <VStack gap={2} width="100%" data-testid="jobagent-conversation-list-panel">
      {isReady ? (
        <Button
          label="Chat mới"
          variant="secondary"
          size="sm"
          isDisabled={isInteractionLocked}
          onClick={() => onCreate(profileId)}
        />
      ) : null}
      <List density="compact" hasDividers header="Conversations">
        {conversations.map((conversation) => (
          <ListItem
            key={conversation.id}
            label={conversation.title}
            description={`Last activity ${formatActivity(conversation.last_opened_at)}`}
            isSelected={conversation.id === selectedConversationId}
            isDisabled={!isReady || isInteractionLocked}
            onClick={
              isReady && !isInteractionLocked
                ? () => onSelect(conversation.id)
                : undefined
            }
            endContent={
              isReady ? (
                <DropdownMenu
                  button={{
                    label: `Actions for conversation ${conversation.title}`,
                    variant: 'ghost',
                    size: 'sm',
                    isDisabled: isInteractionLocked,
                  }}
                  hasChevron={false}
                  items={[
                    {
                      label: 'Delete conversation',
                      isDisabled: isInteractionLocked,
                      onClick: () => onDelete(conversation),
                    },
                  ]}
                />
              ) : null
            }
          />
        ))}
      </List>
      {profileId === null ? (
        <Text type="supporting" color="secondary" as="p">
          Select a profile to view conversations.
        </Text>
      ) : null}
    </VStack>
  );
}

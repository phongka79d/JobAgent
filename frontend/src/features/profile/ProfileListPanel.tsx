import {Button} from '@astryxdesign/core/Button';
import {DropdownMenu} from '@astryxdesign/core/DropdownMenu';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {Text} from '@astryxdesign/core/Text';
import {Token} from '@astryxdesign/core/Token';
import {VStack} from '@astryxdesign/core/VStack';

import type {ProfileListItem, ProfileSetupStatus} from './conversationTypes';

const MAX_VISIBLE_SKILLS = 4;

const SETUP_LABELS: Record<ProfileSetupStatus, string> = {
  awaiting_extraction: 'Awaiting extraction',
  awaiting_approval: 'Awaiting approval',
  extraction_failed: 'Extraction failed',
};

export type ProfileListPanelProps = {
  profiles: readonly ProfileListItem[];
  activeProfileId: string | null;
  isInteractionLocked: boolean;
  onActivate: (profileId: string) => void;
  onRename: (profile: ProfileListItem) => void;
  onReextract: (profile: ProfileListItem) => void;
  onRetrySetup: (profile: ProfileListItem) => void;
  onDelete: (profile: ProfileListItem) => void;
};

function ProfileMetadata({profile}: {profile: ProfileListItem}) {
  const visibleSkills = profile.skill_tags.slice(0, MAX_VISIBLE_SKILLS);
  const overflow = Math.max(0, profile.skill_count - visibleSkills.length);

  return (
    <VStack gap={1}>
      <Text type="supporting" color="secondary" as="span">
        {profile.cv_filename}
      </Text>
      <Text type="supporting" color="secondary" as="span">
        {profile.location ?? 'Location unavailable'}
      </Text>
      {profile.state === 'pending' && profile.setup_status ? (
        <Text type="supporting" color="secondary" as="span">
          {SETUP_LABELS[profile.setup_status]}
        </Text>
      ) : null}
      {visibleSkills.length > 0 ? (
        <HStack gap={1} wrap="wrap">
          {visibleSkills.map((skill) => (
            <Token key={skill.key} label={skill.label} size="sm" color="gray" />
          ))}
          {overflow > 0 ? <Token label={`+${overflow}`} size="sm" color="gray" /> : null}
        </HStack>
      ) : (
        <Text type="supporting" color="secondary" as="span">
          No extracted skills
        </Text>
      )}
    </VStack>
  );
}

function ReadyActions({
  profile,
  isDisabled,
  onActivate,
  onRename,
  onReextract,
  onDelete,
}: {
  profile: ProfileListItem;
  isDisabled: boolean;
  onActivate: (profileId: string) => void;
  onRename: (profile: ProfileListItem) => void;
  onReextract: (profile: ProfileListItem) => void;
  onDelete: (profile: ProfileListItem) => void;
}) {
  return (
    <DropdownMenu
      button={{
        label: `Actions for ${profile.display_name}`,
        variant: 'ghost',
        size: 'sm',
        isDisabled,
      }}
      hasChevron={false}
      items={[
        {
          label: 'Use profile',
          isDisabled: isDisabled || profile.is_active,
          onClick: () => onActivate(profile.id),
        },
        {label: 'Rename', isDisabled, onClick: () => onRename(profile)},
        {
          label: 'Re-extract CV',
          isDisabled: isDisabled || !profile.is_active,
          onClick: () => onReextract(profile),
        },
        {type: 'divider'},
        {
          label: 'Delete profile',
          isDisabled,
          onClick: () => onDelete(profile),
        },
      ]}
    />
  );
}

export function ProfileListPanel({
  profiles,
  activeProfileId,
  isInteractionLocked,
  onActivate,
  onRename,
  onReextract,
  onRetrySetup,
  onDelete,
}: ProfileListPanelProps) {
  return (
    <VStack gap={2} width="100%" data-testid="jobagent-profile-list-panel">
      <Text type="label" as="h2">
        Profiles
      </Text>
      <List density="compact" hasDividers header="CV profiles">
        {profiles.map((profile) => {
          const isPending = profile.state === 'pending';
          const isReady = profile.state === 'ready';
          const pendingActions = isPending ? (
            <HStack gap={1}>
              <Button
                label="Retry"
                size="sm"
                variant="secondary"
                isDisabled={isInteractionLocked}
                onClick={() => onRetrySetup(profile)}
              />
              <Button
                label="Discard"
                size="sm"
                variant="destructive"
                isDisabled={isInteractionLocked}
                onClick={() => onDelete(profile)}
              />
            </HStack>
          ) : isReady ? (
            <ReadyActions
              profile={profile}
              isDisabled={isInteractionLocked}
              onActivate={onActivate}
              onRename={onRename}
              onReextract={onReextract}
              onDelete={onDelete}
            />
          ) : null;

          return (
            <ListItem
              key={profile.id}
              label={profile.display_name}
              description={<ProfileMetadata profile={profile} />}
              endContent={pendingActions}
              isSelected={profile.id === activeProfileId}
            />
          );
        })}
      </List>
    </VStack>
  );
}

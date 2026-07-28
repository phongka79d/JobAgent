import {useEffect, useMemo, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {ButtonGroup} from '@astryxdesign/core/ButtonGroup';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {Token} from '@astryxdesign/core/Token';
import {VStack} from '@astryxdesign/core/VStack';

import type {CvTailoringController} from './state';
import {TailoringSessionDeleteDialog} from './TailoringSessionDeleteDialog';
import {sessionDisplayLabel} from './presentation';
import type {TailoringSessionSummary} from './types';

export type TailoringSessionsPanelProps = {
  readonly controller: CvTailoringController;
  readonly onOpenSession: (sessionId: string) => void;
};

export function legacyTailoringSessionLabel(session: TailoringSessionSummary): string {
  const title = session.job_label?.title?.trim() ?? '';
  const company = session.job_label?.company?.trim() ?? '';
  if (title && company) return `${title} · ${company}`;
  if (title) return title;
  if (company) return company;
  const instruction = session.instruction.trim();
  if (instruction) {
    return instruction.length > 72 ? `${instruction.slice(0, 69)}…` : instruction;
  }
  return 'Untitled tailored CV';
}

export function tailoringSessionLabel(session: TailoringSessionSummary): string {
  return sessionDisplayLabel(session);
}

function statusView(session: TailoringSessionSummary): {
  label: string;
  variant: 'success' | 'warning' | 'error' | 'accent' | 'neutral';
  color: 'green' | 'yellow' | 'red' | 'blue' | 'gray';
} {
  if (session.currentness === 'stale') {
    return {label: 'Needs review', variant: 'warning', color: 'yellow'};
  }
  switch (session.state) {
    case 'generating':
      return {label: 'Creating', variant: 'accent', color: 'blue'};
    case 'ready':
      return {label: 'Ready', variant: 'success', color: 'green'};
    case 'failed':
      return {label: 'Failed', variant: 'error', color: 'red'};
    case 'deleting':
      return {label: 'Deleting', variant: 'neutral', color: 'gray'};
  }
}

function SessionStatus({session}: {readonly session: TailoringSessionSummary}) {
  const status = statusView(session);
  return (
    <HStack gap={1} vAlign="center">
      <StatusDot
        variant={status.variant}
        label={status.label}
        isPulsing={session.state === 'generating'}
      />
      <Token label={status.label} color={status.color} size="sm" />
    </HStack>
  );
}

function sessionDescription(session: TailoringSessionSummary) {
  const timestamp = new Intl.DateTimeFormat('en-CA', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(session.updated_at));
  return `Version ${session.latest_version_number} · ${timestamp}`;
}

export function TailoringSessionsPanel({
  controller,
  onOpenSession,
}: TailoringSessionsPanelProps) {
  const {state} = controller;
  const [deleteTarget, setDeleteTarget] = useState<TailoringSessionSummary | null>(
    null,
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const items = state.sessions.data?.items ?? [];

  useEffect(() => {
    void controller.loadSessions();
  }, [controller.loadSessions, state.profileScopeKey]);

  const selectedLabel = useMemo(
    () => (deleteTarget ? tailoringSessionLabel(deleteTarget) : ''),
    [deleteTarget],
  );

  if (state.sessions.phase === 'loading' && state.sessions.data === null) {
    return (
      <Text type="supporting" role="status" aria-live="polite">
        Loading tailored CVs…
      </Text>
    );
  }

  if (state.sessions.phase === 'error' && items.length === 0) {
    return (
      <EmptyState
        title="Unable to load tailored CVs"
        description="The tailored CV list could not be loaded."
        isCompact
        actions={
          <Button
            label="Retry"
            size="sm"
            onClick={() => void controller.loadSessions()}
          />
        }
      />
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="No tailored CVs yet"
        description="Choose a saved job or ask the assistant to create a tailored CV."
        isCompact
      />
    );
  }

  return (
    <VStack gap={3} width="100%">
      <HStack gap={2} hAlign="between" vAlign="center">
        <Heading level={2}>Tailored CVs</Heading>
        <Button
          label="Refresh"
          size="sm"
          variant="ghost"
          onClick={() => void controller.loadSessions()}
        />
      </HStack>
      <List density="compact" hasDividers header="Tailored CV sessions">
        {items.map((session) => {
          const canRetry =
            session.state === 'failed' && session.latest_version_number === 0;
          const actions = canRetry ? (
            <ButtonGroup label={`Actions for ${tailoringSessionLabel(session)}`} size="sm">
              <Button
                label="Retry"
                variant="secondary"
                isLoading={retryingId === session.id}
                onClick={() => {
                  if (retryingId !== null) return;
                  setRetryingId(session.id);
                  void controller
                    .createAiVersion(session.id, {
                      parent_version_id: null,
                      instruction: '',
                      target_section_ids: [],
                    })
                    .finally(() => setRetryingId(null));
                }}
              />
              <Button
                label="Delete session"
                variant="secondary"
                onClick={() => setDeleteTarget(session)}
              />
            </ButtonGroup>
          ) : undefined;
          return (
            <ListItem
              key={session.id}
              label={tailoringSessionLabel(session)}
              description={
                <VStack gap={1}>
                  <Text type="supporting">{sessionDescription(session)}</Text>
                  {actions}
                </VStack>
              }
              endContent={<SessionStatus session={session} />}
              isSelected={state.selectedSessionId === session.id}
              isDisabled={session.state === 'deleting'}
              onClick={canRetry ? undefined : () => onOpenSession(session.id)}
              data-testid={`jobagent-tailoring-session-${session.id}`}
            />
          );
        })}
      </List>
      <TailoringSessionDeleteDialog
        isOpen={deleteTarget !== null}
        sessionLabel={selectedLabel}
        isDeleting={isDeleting}
        onOpenChange={(isOpen) => {
          if (!isOpen && !isDeleting) setDeleteTarget(null);
        }}
        onConfirm={async () => {
          if (deleteTarget === null || isDeleting) return;
          setIsDeleting(true);
          const deleted = await controller.deleteSession(deleteTarget.id);
          setIsDeleting(false);
          if (deleted) setDeleteTarget(null);
        }}
      />
    </VStack>
  );
}

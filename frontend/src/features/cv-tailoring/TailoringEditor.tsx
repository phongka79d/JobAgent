import {useEffect, useMemo, useRef, useState} from 'react';
import {AlertDialog} from '@astryxdesign/core/AlertDialog';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {Layout, LayoutContent, LayoutHeader} from '@astryxdesign/core/Layout';
import {Section} from '@astryxdesign/core/Section';
import {Selector} from '@astryxdesign/core/Selector';
import {StackItem} from '@astryxdesign/core/Stack';
import {Tab, TabList} from '@astryxdesign/core/TabList';
import {Text} from '@astryxdesign/core/Text';
import {TextArea} from '@astryxdesign/core/TextArea';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Token} from '@astryxdesign/core/Token';
import {Toolbar} from '@astryxdesign/core/Toolbar';
import {VStack} from '@astryxdesign/core/VStack';
import {useMediaQuery} from '@astryxdesign/core/hooks';

import {TAILORING_COPY} from './copy';
import type {CvTailoringController, TailoringSafeError} from './state';
import {TailoredSectionEditor} from './TailoredSectionEditor';
import {TailoringPdfPreview} from './TailoringPdfPreview';
import {TailoringSessionDeleteDialog} from './TailoringSessionDeleteDialog';
import {sessionDisplayLabel} from './presentation';
import {
  tailoringFieldId,
  tailoringIssueId,
  tailoringSectionId,
  type TailoredCVContent,
  type TailoredSection,
  type TailoringVersionSummary,
} from './types';
import './cv-tailoring.css';

export type TailoringEditorProps = {
  readonly controller: CvTailoringController;
  readonly onBackToChat: () => void;
  readonly onEditProfile: () => void;
  readonly canCreateFresh: boolean;
  readonly onCreateFresh?: () => void;
  readonly onReloadLatest: () => void;
  readonly artifactUrls?: {
    readonly source: (versionId: string) => string;
    readonly pdf: (versionId: string) => string;
  };
  readonly mobileLayout?: boolean;
};

type MobileView = 'content' | 'preview';

function safeErrorText(error: TailoringSafeError | null): string | null {
  if (error === null) return null;
  switch (error.code) {
    case 'TAILORING_PARENT_CONFLICT':
      return 'A newer version exists. Your draft is preserved.';
    case 'TAILORING_GROUNDING_FAILED':
      return 'Source support warning';
    case 'TAILORING_COMPILE_FAILED':
      return 'The PDF could not be created. Your draft and previous PDF are preserved.';
    case 'TAILORING_SOURCE_STALE':
      return 'The source changed. Create a new session.';
    case 'STREAM_DISCONNECTED':
      return 'The connection was lost. Completion has not been confirmed.';
    default:
      return 'The CV request could not be completed.';
  }
}

function safeErrorDescription(error: TailoringSafeError | null): string | undefined {
  if (error?.code === 'TAILORING_GROUNDING_FAILED') {
    return 'Manual edits are still available. Use source evidence, undo the flagged field, or retry with AI.';
  }
  return undefined;
}

function safeErrorStatus(
  error: TailoringSafeError | null,
): 'error' | 'warning' {
  return error?.code === 'TAILORING_GROUNDING_FAILED' ? 'warning' : 'error';
}

function replaceSection(
  content: TailoredCVContent,
  section: TailoredSection,
): TailoredCVContent {
  return {
    ...content,
    sections: content.sections.map((candidate) =>
      candidate.id === section.id ? section : candidate,
    ),
  };
}

function HeaderFacts({
  content,
  onEditProfile,
}: {
  readonly content: TailoredCVContent;
  readonly onEditProfile: () => void;
}) {
  const facts = [
    ['Full name', content.header.full_name],
    ['Location', content.header.location],
    ['Phone', content.header.phone],
    ['Email', content.header.email],
    ['GitHub', content.header.github_url],
  ] as const;
  return (
    <Section variant="muted">
      <VStack gap={3}>
        <HStack gap={2} hAlign="between" vAlign="center" wrap="wrap">
          <Heading level={2}>Approved profile information</Heading>
          <Button
            label="Edit profile information"
            size="sm"
            variant="secondary"
            onClick={onEditProfile}
          />
        </HStack>
        {facts.map(([label, value]) =>
          value ? (
            <TextInput
              key={label}
              label={label}
              value={value}
              isDisabled
              disabledMessage="This information is managed by the approved profile."
            />
          ) : null,
        )}
      </VStack>
    </Section>
  );
}

function VersionLineage({
  versions,
  selectedVersionId,
}: {
  readonly versions: readonly TailoringVersionSummary[];
  readonly selectedVersionId: string | null;
}) {
  const sorted = [...versions].sort(
    (left, right) => left.version_number - right.version_number,
  );
  const depths = new Map<string, number>();
  const rows = sorted.map((version) => {
    const parentDepth = version.parent_version_id
      ? (depths.get(version.parent_version_id) ?? 0)
      : 0;
    const depth = parentDepth + 1;
    depths.set(version.id, depth);
    return {version, depth};
  });

  return (
    <VStack gap={1} role="tree" aria-label="Version lineage">
      <Text role="treeitem" aria-level={1} type="supporting">
        Base CV
      </Text>
      {rows.map(({version, depth}) => (
        <Text
          key={version.id}
          role="treeitem"
          aria-level={depth + 1}
          aria-selected={version.id === selectedVersionId}
          type="supporting"
        >
          {`Version ${version.version_number} - ${
            version.created_by === 'ai' ? 'AI' : 'You'
          }`}
        </Text>
      ))}
    </VStack>
  );
}

export function TailoringEditor({
  controller,
  onBackToChat,
  onEditProfile,
  canCreateFresh,
  onCreateFresh,
  onReloadLatest,
  artifactUrls,
  mobileLayout,
}: TailoringEditorProps) {
  const {state} = controller;
  const detail = state.detail.data;
  const draft = state.draft;
  const matchesMobile = useMediaQuery('(max-width: 48rem)');
  const isMobile = mobileLayout ?? matchesMobile;
  const [mobileView, setMobileView] = useState<MobileView>('content');
  const [aiTarget, setAiTarget] = useState<{
    sectionId: string;
    heading: string;
  } | null>(null);
  const [aiInstruction, setAiInstruction] = useState('');
  const [isAiPending, setIsAiPending] = useState(false);
  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const saveGuard = useRef(false);
  const activeError = state.detail.error ?? state.stream.error;
  const errorText = safeErrorText(activeError);
  const errorDescription = safeErrorDescription(activeError);
  const issues = state.stream.error?.issues ?? state.detail.error?.issues ?? [];
  const [evidenceTarget, setEvidenceTarget] = useState<{sectionId: string; key: number} | null>(null);

  useEffect(() => {
    const target = state.pendingFocus?.issue;
    if (!target) return;
    const id = target.item_index === null || target.field === 'section'
      ? tailoringSectionId(target.section_id)
      : tailoringFieldId(target.section_id, target.item_index, target.field);
    const field = document.getElementById(id)
      ?? document.querySelector<HTMLElement>(`[name="${id}"]`)
      ?? document.querySelector<HTMLElement>(`[name^="${id}-"]`);
    field?.focus();
  }, [state.pendingFocus]);

  useEffect(() => {
    const request = state.retryRequest;
    if (!request) return;
    setAiTarget({sectionId: request.issue.section_id, heading: request.issue.section_heading});
    setAiInstruction(request.instruction);
  }, [state.retryRequest]);

  const versionOptions = useMemo(
    () =>
      (detail?.versions ?? []).map((version) => ({
        value: version.id,
        label: `Version ${version.version_number} · ${
          version.created_by === 'ai' ? 'AI' : 'You'
        }`,
      })),
    [detail?.versions],
  );

  if (detail === null || draft === null) {
    return (
      <EmptyState
        title="No tailored CV session open"
        description="Choose a tailored CV session to open the editor."
        actions={<Button label="Back to chat" onClick={onBackToChat} />}
      />
    );
  }

  const selectedVersion = detail.selected_version;
  const isStale = detail.session.currentness === 'stale';
  const isStreamPending = state.stream.phase === 'loading';
  const editingDisabled = isStale || isStreamPending || isSaving || isAiPending;

  const editorContent = (
    <VStack gap={4} width="100%">
      <HeaderFacts content={draft} onEditProfile={onEditProfile} />
      {draft.sections.map((section) => (
          <TailoredSectionEditor
          key={section.id}
          section={section}
          evidence={detail.evidence.filter(
            (fact) => fact.section_id === section.id,
          )}
          isDisabled={editingDisabled}
          onChange={(next) => controller.setDraft(replaceSection(draft, next))}
          onAskAi={(sectionId, heading) =>
            setAiTarget({sectionId, heading})
          }
          issues={issues.filter((issue) => issue.section_id === section.id)}
          isEvidenceOpen={evidenceTarget?.sectionId === section.id}
          evidenceFocusKey={evidenceTarget?.sectionId === section.id ? evidenceTarget.key : 0}
        />
      ))}
    </VStack>
  );

  const previewContent = (
    <TailoringPdfPreview
      versionId={selectedVersion?.id ?? null}
      sourceAvailable={detail.source_available}
      pdfAvailable={detail.pdf_available}
      artifactLabel={sessionDisplayLabel(detail.session)}
      sourceUrl={artifactUrls?.source}
      pdfUrl={artifactUrls?.pdf}
    />
  );

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider label="Tailored CV toolbar">
          <Toolbar
            label="Tailored CV actions"
            size="sm"
            startContent={
              <HStack gap={2} vAlign="center" wrap="wrap">
                <Button
                  label="Back to chat"
                  variant="ghost"
                  onClick={onBackToChat}
                />
                <Heading level={1}>Tailored CV</Heading>
                <Token
                  label={isStale ? 'Needs review' : 'Current'}
                  color={isStale ? 'yellow' : 'green'}
                  size="sm"
                />
                <Text type="supporting">
                  {sessionDisplayLabel(detail.session)}
                </Text>
              </HStack>
            }
            endContent={
              <HStack gap={2} wrap="wrap">
                <Button
                  label="Delete session"
                  variant="ghost"
                  onClick={() => setDeleteOpen(true)}
                />
                <Button
                  label="Save version"
                  variant="primary"
                  isDisabled={editingDisabled || !state.draftDirty}
                  isLoading={isSaving}
                  onClick={() => {
                    if (saveGuard.current) return;
                    saveGuard.current = true;
                    setIsSaving(true);
                    void controller.saveManualVersion().finally(() => {
                      saveGuard.current = false;
                      setIsSaving(false);
                    });
                  }}
                />
              </HStack>
            }
          />
        </LayoutHeader>
      }
    >
      <LayoutContent label="Tailored CV editor">
        <VStack gap={3} width="100%" height="100%">
          <Section variant="transparent" padding={3} dividers={['bottom']}>
            <HStack gap={3} hAlign="between" vAlign="end" wrap="wrap">
              <Selector
                label="Version CV"
                options={versionOptions}
                value={state.selectedVersionId ?? undefined}
                isDisabled={isStreamPending || versionOptions.length === 0}
                onChange={(versionId) => {
                  if (state.draftDirty) {
                    setPendingVersionId(versionId);
                    return;
                  }
                  void controller.selectVersion(versionId);
                }}
              />
              <VStack gap={1}>
                <Text type="supporting">
                  {selectedVersion?.created_by === 'ai' ? 'Created by AI' : 'Created by you'}
                </Text>
                <Text type="supporting">
                  {selectedVersion
                    ? new Intl.DateTimeFormat('en-CA', {
                        dateStyle: 'short',
                        timeStyle: 'short',
                      }).format(new Date(selectedVersion.created_at))
                    : 'No version selected'}
                </Text>
                {selectedVersion ? (
                  <Text type="supporting">
                    {TAILORING_COPY.pageCount(selectedVersion.page_count)}
                  </Text>
                ) : null}
              </VStack>
            </HStack>
            <VersionLineage
              versions={detail.versions}
              selectedVersionId={state.selectedVersionId}
            />
          </Section>

          {isStale ? (
            <Banner
              status="warning"
              title="Source data changed"
              description="This session remains readable and downloadable, but cannot create another version."
              container="section"
              endContent={
                <Button
                  label="Create a new session from current data"
                  size="sm"
                  isDisabled={!canCreateFresh || onCreateFresh === undefined}
                  onClick={onCreateFresh}
                />
              }
            />
          ) : null}

          {selectedVersion?.page_warning ? (
            <Banner
              status="warning"
              title={selectedVersion.page_warning}
              container="section"
            />
          ) : null}

          {detail.fit_warning ? (
            <Banner
              status="warning"
              title="JD fit warning"
              description={detail.fit_warning}
              container="section"
            />
          ) : null}

          {state.lastOutcome === 'no_change' ? (
            <VStack role="status" aria-live="polite">
              <Banner
                status="info"
                title={state.lastOutcomeSource === 'manual' ? TAILORING_COPY.noChangeManual : TAILORING_COPY.noChangeAi}
                container="section"
              />
            </VStack>
          ) : null}

          {issues.length > 0 ? (
            <VStack gap={2} role="status" aria-live="polite">
              {issues.map((issue) => (
                <Section key={tailoringIssueId(issue)} variant="muted" padding={3}>
                  <VStack gap={2}>
                    <Text id={tailoringIssueId(issue)} type="body">{issue.section_heading}: {TAILORING_COPY.issueReasons[issue.reason]}</Text>
                    <HStack gap={2} wrap="wrap">
                      <Button label="Focus field" size="sm" variant="secondary" onClick={() => controller.focusIssue(issue)} />
                      <Button label="View source" size="sm" variant="secondary" onClick={() => setEvidenceTarget({sectionId: issue.section_id, key: Date.now()})} />
                      <Button label="Undo change" size="sm" variant="secondary" onClick={() => controller.undoIssue(issue)} />
                      <Button label="Try again" size="sm" variant="secondary" onClick={() => controller.retryIssue(issue)} />
                    </HStack>
                  </VStack>
                </Section>
              ))}
            </VStack>
          ) : null}

          {errorText ? (
            <VStack role="status" aria-live="polite">
              <Banner
                status={safeErrorStatus(activeError)}
                title={errorText}
                description={errorDescription}
                container="section"
                endContent={
                  state.conflict ? (
                    <Button
                      label="Load latest version"
                      size="sm"
                      onClick={onReloadLatest}
                    />
                  ) : undefined
                }
              />
            </VStack>
          ) : null}

          {isStreamPending ? (
            <Text type="supporting" role="status" aria-live="polite">
                      AI is creating a tailored CV version…
            </Text>
          ) : null}

          {isMobile ? (
            <VStack gap={3} width="100%">
              <TabList
                role="tablist"
                value={mobileView}
                onChange={(value) => setMobileView(value as MobileView)}
                layout="fill"
                hasDivider
                aria-label="CV view mode"
              >
                <Tab
                  role="tab"
                  value="content"
                  label="Content"
                  aria-selected={mobileView === 'content'}
                />
                <Tab
                  role="tab"
                  value="preview"
                  label="Preview"
                  aria-selected={mobileView === 'preview'}
                />
              </TabList>
              <StackItem
                as="section"
                isScrollable
                data-scroll-owner="viewport"
                role="tabpanel"
                aria-label={mobileView === 'content' ? 'Content' : 'Preview'}
              >
                {mobileView === 'content' ? editorContent : previewContent}
              </StackItem>
            </VStack>
          ) : (
            <HStack
              gap={4}
              width="100%"
              height="100%"
              className="jobagent-tailoring-desktop-split"
            >
              <StackItem size="fill" isScrollable as="section" data-scroll-owner="viewport" aria-label="Content">
                {editorContent}
              </StackItem>
              <StackItem size="fill" isScrollable as="section" data-scroll-owner="viewport" aria-label="Preview">
                {previewContent}
              </StackItem>
            </HStack>
          )}
        </VStack>
      </LayoutContent>

      <Dialog
        isOpen={aiTarget !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen && !isAiPending) {
            setAiTarget(null);
            setAiInstruction('');
          }
        }}
        purpose="form"
      >
        <VStack gap={4} padding={4}>
          <DialogHeader
            title={`Ask AI to revise ${aiTarget?.heading ?? 'this section'}`}
            onOpenChange={(isOpen) => {
              if (!isOpen && !isAiPending) setAiTarget(null);
            }}
          />
          <TextArea
              label="Revision request"
            value={aiInstruction}
            rows={5}
            maxLength={4_000}
            isDisabled={isAiPending}
            onChange={setAiInstruction}
          />
          <HStack gap={2} hAlign="end">
            <Button
              label="Cancel"
              variant="secondary"
              isDisabled={isAiPending}
              onClick={() => setAiTarget(null)}
            />
            <Button
              label="Send to AI"
              variant="primary"
              isLoading={isAiPending}
              isDisabled={
                aiTarget === null ||
                aiInstruction.trim() === '' ||
                state.selectedVersionId === null
              }
              onClick={() => {
                if (
                  aiTarget === null ||
                  state.selectedVersionId === null ||
                  isAiPending
                ) {
                  return;
                }
                setIsAiPending(true);
                void controller
                  .createAiVersion(detail.session.id, {
                    parent_version_id: state.selectedVersionId,
                    instruction: aiInstruction.trim(),
                    target_section_ids: [aiTarget.sectionId],
                  })
                  .then((success) => {
                    if (success) {
                      setAiTarget(null);
                      setAiInstruction('');
                    }
                  })
                  .finally(() => setIsAiPending(false));
              }}
            />
          </HStack>
        </VStack>
      </Dialog>

      <AlertDialog
        isOpen={pendingVersionId !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen) setPendingVersionId(null);
        }}
        title="Discard unsaved changes?"
        description="Changing versions will replace the current draft with saved content."
        actionLabel="Discard changes"
        cancelLabel="Stay"
        onAction={() => {
          if (pendingVersionId === null) return;
          const versionId = pendingVersionId;
          setPendingVersionId(null);
          void controller.selectVersion(versionId, true);
        }}
      />

      <TailoringSessionDeleteDialog
        isOpen={deleteOpen}
        sessionLabel={
          sessionDisplayLabel(detail.session)
        }
        isDeleting={isDeleting}
        onOpenChange={(isOpen) => {
          if (!isOpen && !isDeleting) setDeleteOpen(false);
        }}
        onConfirm={async () => {
          if (isDeleting) return;
          setIsDeleting(true);
          const deleted = await controller.deleteSession(detail.session.id);
          setIsDeleting(false);
          if (deleted) {
            setDeleteOpen(false);
            onBackToChat();
          }
        }}
      />
    </Layout>
  );
}

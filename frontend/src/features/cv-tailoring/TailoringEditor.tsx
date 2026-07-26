import {useMemo, useRef, useState} from 'react';
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

import type {CvTailoringController, TailoringSafeError} from './state';
import {TailoredSectionEditor} from './TailoredSectionEditor';
import {TailoringPdfPreview} from './TailoringPdfPreview';
import {TailoringSessionDeleteDialog} from './TailoringSessionDeleteDialog';
import type {TailoredCVContent, TailoredSection} from './types';
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
      return 'Có version mới hơn. Bản nháp của bạn vẫn được giữ.';
    case 'TAILORING_GROUNDING_FAILED':
      return 'Nội dung chưa vượt qua kiểm tra nguồn. Bản nháp vẫn được giữ.';
    case 'TAILORING_COMPILE_FAILED':
      return 'Không thể tạo PDF. Bản nháp và PDF trước đó vẫn được giữ.';
    case 'TAILORING_SOURCE_STALE':
      return 'Dữ liệu nguồn đã thay đổi. Hãy tạo một phiên mới.';
    case 'STREAM_DISCONNECTED':
      return 'Mất kết nối khi tạo CV. Trạng thái bền vững chưa xác nhận hoàn tất.';
    default:
      return 'Không thể hoàn tất yêu cầu CV.';
  }
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
    ['Họ và tên', content.header.full_name],
    ['Địa điểm', content.header.location],
    ['Điện thoại', content.header.phone],
    ['Email', content.header.email],
    ['GitHub', content.header.github_url],
  ] as const;
  return (
    <Section variant="muted">
      <VStack gap={3}>
        <HStack gap={2} hAlign="between" vAlign="center" wrap="wrap">
          <Heading level={2}>Thông tin đã duyệt</Heading>
          <Button
            label="Sửa thông tin Profile"
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
              disabledMessage="Thông tin này được quản lý trong Profile đã duyệt."
            />
          ) : null,
        )}
      </VStack>
    </Section>
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
  const errorText = safeErrorText(state.detail.error ?? state.stream.error);

  const versionOptions = useMemo(
    () =>
      (detail?.versions ?? []).map((version) => ({
        value: version.id,
        label: `Version ${version.version_number} · ${
          version.created_by === 'ai' ? 'AI' : 'Bạn'
        }`,
      })),
    [detail?.versions],
  );

  if (detail === null || draft === null) {
    return (
      <EmptyState
        title="Chưa mở phiên CV"
        description="Chọn một phiên CV đã chỉnh để mở editor."
        actions={<Button label="Quay lại chat" onClick={onBackToChat} />}
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
        />
      ))}
    </VStack>
  );

  const previewContent = (
    <TailoringPdfPreview
      versionId={selectedVersion?.id ?? null}
      sourceAvailable={detail.source_available}
      pdfAvailable={detail.pdf_available}
      sourceUrl={artifactUrls?.source}
      pdfUrl={artifactUrls?.pdf}
    />
  );

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider label="Thanh công cụ CV đã chỉnh">
          <Toolbar
            label="Thao tác CV đã chỉnh"
            size="sm"
            startContent={
              <HStack gap={2} vAlign="center" wrap="wrap">
                <Button
                  label="Quay lại chat"
                  variant="ghost"
                  onClick={onBackToChat}
                />
                <Heading level={1}>CV đã chỉnh</Heading>
                <Token
                  label={isStale ? 'Dữ liệu cũ' : 'Hiện tại'}
                  color={isStale ? 'yellow' : 'green'}
                  size="sm"
                />
              </HStack>
            }
            endContent={
              <HStack gap={2} wrap="wrap">
                <Button
                  label="Xóa phiên"
                  variant="ghost"
                  onClick={() => setDeleteOpen(true)}
                />
                <Button
                  label="Lưu version & tạo PDF"
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
      <LayoutContent label="Editor CV đã chỉnh">
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
                  {selectedVersion?.created_by === 'ai' ? 'Tạo bởi AI' : 'Tạo bởi bạn'}
                </Text>
                <Text type="supporting">
                  {selectedVersion
                    ? new Intl.DateTimeFormat('vi-VN', {
                        dateStyle: 'short',
                        timeStyle: 'short',
                      }).format(new Date(selectedVersion.created_at))
                    : 'Chưa có version'}
                </Text>
                {selectedVersion ? (
                  <Text type="supporting">
                    {selectedVersion.page_count} trang
                  </Text>
                ) : null}
              </VStack>
            </HStack>
          </Section>

          {isStale ? (
            <Banner
              status="warning"
              title="Dữ liệu nguồn đã thay đổi"
              description="Phiên cũ vẫn xem và tải được nhưng không thể ghi thêm version."
              container="section"
              endContent={
                <Button
                  label="Tạo phiên mới từ dữ liệu hiện tại"
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

          {errorText ? (
            <VStack role="status" aria-live="polite">
              <Banner
                status="error"
                title={errorText}
                container="section"
                endContent={
                  state.conflict ? (
                    <Button
                      label="Tải version mới nhất"
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
              AI đang tạo version CV…
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
                aria-label="Chế độ xem CV"
              >
                <Tab
                  role="tab"
                  value="content"
                  label="Nội dung"
                  aria-selected={mobileView === 'content'}
                />
                <Tab
                  role="tab"
                  value="preview"
                  label="Xem trước"
                  aria-selected={mobileView === 'preview'}
                />
              </TabList>
              {mobileView === 'content' ? editorContent : previewContent}
            </VStack>
          ) : (
            <HStack
              gap={4}
              width="100%"
              height="100%"
              className="jobagent-tailoring-desktop-split"
            >
              <StackItem size="fill" isScrollable as="section">
                {editorContent}
              </StackItem>
              <StackItem size="fill" isScrollable as="section">
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
            title={`Nhờ AI chỉnh ${aiTarget?.heading ?? 'section'}`}
            onOpenChange={(isOpen) => {
              if (!isOpen && !isAiPending) setAiTarget(null);
            }}
          />
          <TextArea
            label="Yêu cầu chỉnh sửa"
            value={aiInstruction}
            rows={5}
            maxLength={4_000}
            isDisabled={isAiPending}
            onChange={setAiInstruction}
          />
          <HStack gap={2} hAlign="end">
            <Button
              label="Hủy"
              variant="secondary"
              isDisabled={isAiPending}
              onClick={() => setAiTarget(null)}
            />
            <Button
              label="Gửi cho AI"
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
        title="Bỏ thay đổi chưa lưu?"
        description="Chuyển version sẽ thay bản nháp hiện tại bằng nội dung đã lưu."
        actionLabel="Bỏ thay đổi"
        cancelLabel="Ở lại"
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
          detail.session.job_label?.title ?? detail.session.instruction ?? 'CV đã chỉnh'
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

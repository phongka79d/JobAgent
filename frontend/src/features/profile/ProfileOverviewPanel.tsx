import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {FileInput} from '@astryxdesign/core/FileInput';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import type {PendingProfileReview, ProfileUploadConflict} from './types';

const MAX_PDF_BYTES = 10 * 1024 * 1024;

type ProfileStateVariant = 'success' | 'neutral' | 'warning' | 'error';

export type ProfileOverviewPanelProps = {
  stateLabel: string;
  stateVariant: ProfileStateVariant;
  cvName: string;
  selectedFile: File | null;
  loadError: string | null;
  uploadError: string | null;
  uploadLabel: string;
  isUploadDisabled: boolean;
  isUploading: boolean;
  disabledReason?: string;
  pendingReview: PendingProfileReview | null;
  uploadConflict?: ProfileUploadConflict | null;
  isDiscardingPendingReview?: boolean;
  pendingReviewDiscardError?: string | null;
  canViewDownload: boolean;
  onFileChange: (files: File | File[] | null) => void;
  onUpload: (files: File | File[] | null) => Promise<void>;
  onReviewPendingChanges: () => void;
  onProfileReextractConflict?: (operationId: string) => void;
  onAgentPendingReview?: (profileId: string, revision: string) => void;
  onDiscardPendingReview: () => void;
  onViewDownload: () => void;
  onManageCvs?: () => void;
};

export function ProfileOverviewPanel({
  stateLabel,
  stateVariant,
  cvName,
  selectedFile,
  loadError,
  uploadError,
  uploadLabel,
  isUploadDisabled,
  isUploading,
  disabledReason,
  pendingReview,
  uploadConflict = null,
  isDiscardingPendingReview = false,
  pendingReviewDiscardError = null,
  canViewDownload,
  onFileChange,
  onUpload,
  onReviewPendingChanges,
  onProfileReextractConflict,
  onAgentPendingReview,
  onDiscardPendingReview,
  onViewDownload,
  onManageCvs,
}: ProfileOverviewPanelProps) {
  const pendingReviewDescription = pendingReview?.can_review
    ? 'Approve or discard the pending profile review before uploading another CV.'
    : 'This pending profile review no longer matches the active CV. Discard it before uploading another CV.';
  const pendingReviewAction = pendingReview ? (
    pendingReview.can_review ? (
      <Button
        label="Review pending changes"
        variant="secondary"
        size="sm"
        onClick={onReviewPendingChanges}
      />
    ) : (
      <Button
        label="Discard pending review"
        variant="secondary"
        size="sm"
        isLoading={isDiscardingPendingReview}
        onClick={onDiscardPendingReview}
      />
    )
  ) : undefined;

  const uploadConflictAction = uploadConflict?.code === 'PROFILE_REEXTRACT_IN_PROGRESS'
    ? <Button label="Check re-extraction" variant="secondary" size="sm" onClick={() => onProfileReextractConflict?.(uploadConflict.operation_id)} />
    : uploadConflict?.review_source === 'reextract'
      ? <Button label="Review changes" variant="secondary" size="sm" onClick={() => onProfileReextractConflict?.(uploadConflict.operation_id)} />
      : uploadConflict
        ? <Button label="Review changes" variant="secondary" size="sm" onClick={() => onAgentPendingReview?.(uploadConflict.profile_id, uploadConflict.review_revision)} />
        : undefined;

  return (
    <VStack
      gap={3}
      padding={0}
      width="100%"
      data-testid="jobagent-cv-sidebar-body"
    >
      <MetadataList columns="single" label={{position: 'top'}}>
        <MetadataListItem label="Profile state">
          <HStack gap={2} vAlign="center">
            <StatusDot variant={stateVariant} label={stateLabel} />
            <Text type="body" data-testid="jobagent-profile-state">
              {stateLabel}
            </Text>
          </HStack>
        </MetadataListItem>
        <MetadataListItem label="Active CV">
          <Text
            type="body"
            maxLines={2}
            data-testid="jobagent-active-cv-filename"
          >
            {cvName}
          </Text>
        </MetadataListItem>
      </MetadataList>

      {loadError ? (
        <Banner
          status="error"
          title="Profile load failed"
          description={loadError}
          container="card"
        />
      ) : null}

      {uploadError ? (
        <Banner
          status="error"
          title="Upload failed"
          description={
            pendingReview && !pendingReview.can_review
              ? pendingReviewDescription
              : uploadError
          }
          endContent={uploadConflictAction ?? pendingReviewAction}
          container="card"
          data-testid="jobagent-cv-upload-error"
        />
      ) : null}
      {pendingReviewDiscardError ? (
        <Banner
          status="error"
          title="Pending profile review could not be discarded"
          description={pendingReviewDiscardError}
          container="card"
        />
      ) : null}
      {!uploadError && pendingReview ? (
        <Banner
          status="warning"
          title="Pending profile review"
          description={pendingReviewDescription}
          endContent={pendingReviewAction}
          container="card"
        />
      ) : null}

      <FileInput
        label={uploadLabel}
        value={selectedFile}
        onChange={onFileChange}
        changeAction={onUpload}
        accept="application/pdf,.pdf"
        maxSize={MAX_PDF_BYTES}
        mode="input"
        isDisabled={isUploadDisabled || isUploading}
        disabledMessage={disabledReason}
        isLoading={isUploading}
        placeholder="Choose PDF..."
        description="PDF only, up to 10 MB / 10 pages"
        data-testid="jobagent-cv-upload"
      />

      <Button
        label="View / download CV"
        variant="secondary"
        size="sm"
        isDisabled={!canViewDownload}
        onClick={onViewDownload}
        data-testid="jobagent-cv-download"
      />
      {onManageCvs ? (
        <Button
          label="Manage CVs"
          variant="secondary"
          size="sm"
          onClick={onManageCvs}
        />
      ) : null}
    </VStack>
  );
}

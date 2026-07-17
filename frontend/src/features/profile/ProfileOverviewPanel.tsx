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
  canViewDownload: boolean;
  onFileChange: (files: File | File[] | null) => void;
  onUpload: (files: File | File[] | null) => Promise<void>;
  onViewDownload: () => void;
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
  canViewDownload,
  onFileChange,
  onUpload,
  onViewDownload,
}: ProfileOverviewPanelProps) {
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
          description={uploadError}
          container="card"
          data-testid="jobagent-cv-upload-error"
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
    </VStack>
  );
}

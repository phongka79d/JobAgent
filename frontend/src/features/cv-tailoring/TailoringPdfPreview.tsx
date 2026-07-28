import {AspectRatio} from '@astryxdesign/core/AspectRatio';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {VStack} from '@astryxdesign/core/VStack';

import {tailoringPdfUrl} from './api';
import {TailoringVersionActions} from './TailoringVersionActions';

export type TailoringPdfPreviewProps = {
  readonly versionId: string | null;
  readonly sourceAvailable: boolean;
  readonly pdfAvailable: boolean;
  readonly artifactLabel?: string;
  readonly sourceUrl?: (versionId: string) => string;
  readonly pdfUrl?: (versionId: string) => string;
};

export function TailoringPdfPreview({
  versionId,
  sourceAvailable,
  pdfAvailable,
  artifactLabel,
  sourceUrl,
  pdfUrl = tailoringPdfUrl,
}: TailoringPdfPreviewProps) {
  if (versionId === null) {
    return (
      <EmptyState
        title="No preview available"
        description="Complete a version to preview the PDF."
        isCompact
      />
    );
  }
  return (
    <VStack gap={3} width="100%">
      {pdfAvailable ? (
        <AspectRatio ratio={8.5 / 11}>
          <iframe
            className="jobagent-tailoring-pdf-frame"
            src={pdfUrl(versionId)}
            title="Tailored CV PDF preview"
          />
        </AspectRatio>
      ) : (
        <EmptyState
          title="PDF not ready"
          description="The content is preserved so you can try again."
          isCompact
        />
      )}
      <TailoringVersionActions
        versionId={versionId}
        sourceAvailable={sourceAvailable}
        pdfAvailable={pdfAvailable}
        artifactLabel={artifactLabel}
        sourceUrl={sourceUrl}
        pdfUrl={pdfUrl}
      />
    </VStack>
  );
}

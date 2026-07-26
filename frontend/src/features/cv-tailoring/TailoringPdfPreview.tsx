import {AspectRatio} from '@astryxdesign/core/AspectRatio';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {VStack} from '@astryxdesign/core/VStack';

import {tailoringPdfUrl} from './api';
import {TailoringVersionActions} from './TailoringVersionActions';

export type TailoringPdfPreviewProps = {
  readonly versionId: string | null;
  readonly sourceAvailable: boolean;
  readonly pdfAvailable: boolean;
  readonly sourceUrl?: (versionId: string) => string;
  readonly pdfUrl?: (versionId: string) => string;
};

export function TailoringPdfPreview({
  versionId,
  sourceAvailable,
  pdfAvailable,
  sourceUrl,
  pdfUrl = tailoringPdfUrl,
}: TailoringPdfPreviewProps) {
  if (versionId === null) {
    return (
      <EmptyState
        title="Chưa có bản xem trước"
        description="Hoàn tất một version để xem PDF."
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
            title="Xem trước PDF CV"
          />
        </AspectRatio>
      ) : (
        <EmptyState
          title="PDF chưa sẵn sàng"
          description="Bản nội dung vẫn được giữ nguyên để bạn thử lại."
          isCompact
        />
      )}
      <TailoringVersionActions
        versionId={versionId}
        sourceAvailable={sourceAvailable}
        pdfAvailable={pdfAvailable}
        sourceUrl={sourceUrl}
        pdfUrl={pdfUrl}
      />
    </VStack>
  );
}

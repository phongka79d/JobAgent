import {HStack} from '@astryxdesign/core/HStack';
import {Link} from '@astryxdesign/core/Link';

import {tailoringPdfUrl, tailoringSourceUrl} from './api';

export type TailoringVersionActionsProps = {
  readonly versionId: string;
  readonly sourceAvailable: boolean;
  readonly pdfAvailable: boolean;
  readonly sourceUrl?: (versionId: string) => string;
  readonly pdfUrl?: (versionId: string) => string;
};

export function TailoringVersionActions({
  versionId,
  sourceAvailable,
  pdfAvailable,
  sourceUrl = tailoringSourceUrl,
  pdfUrl = tailoringPdfUrl,
}: TailoringVersionActionsProps) {
  return (
    <HStack gap={3} wrap="wrap" aria-label="Tải version CV">
      {sourceAvailable ? (
        <Link href={sourceUrl(versionId)} isStandalone>
          Tải file .tex
        </Link>
      ) : null}
      {pdfAvailable ? (
        <Link
          href={pdfUrl(versionId)}
          target="_blank"
          rel="noopener noreferrer"
          isStandalone
        >
          Tải PDF
        </Link>
      ) : null}
    </HStack>
  );
}

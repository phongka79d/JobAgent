import {useState} from 'react';
import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

import {downloadArtifact, safeArtifactName} from '../../lib/api/download';
import {tailoringPdfUrl, tailoringSourceUrl} from './api';
import {TAILORING_COPY} from './copy';

export type TailoringVersionActionsProps = {
  readonly versionId: string;
  readonly sourceAvailable: boolean;
  readonly pdfAvailable: boolean;
  readonly artifactLabel?: string;
  readonly sourceUrl?: (versionId: string) => string;
  readonly pdfUrl?: (versionId: string) => string;
};

export function TailoringVersionActions({
  versionId,
  sourceAvailable,
  pdfAvailable,
  artifactLabel = 'tailored-cv',
  sourceUrl = tailoringSourceUrl,
  pdfUrl = tailoringPdfUrl,
}: TailoringVersionActionsProps) {
  const [error, setError] = useState<string | null>(null);
  const download = async (kind: 'pdf' | 'tex') => {
    setError(null);
    try {
      await downloadArtifact(
        kind === 'pdf' ? pdfUrl(versionId) : sourceUrl(versionId),
        safeArtifactName(artifactLabel, kind),
      );
    } catch {
      setError(kind === 'pdf' ? TAILORING_COPY.pdfDownloadError : TAILORING_COPY.latexDownloadError);
    }
  };

  return (
    <VStack gap={2}>
      <HStack gap={2} wrap="wrap" aria-label="Tailored CV artifacts">
        {pdfAvailable ? <Button label={TAILORING_COPY.previewPdf} variant="secondary" onClick={() => window.open(pdfUrl(versionId), '_blank', 'noopener,noreferrer')} /> : null}
        {pdfAvailable ? <Button label={TAILORING_COPY.downloadPdf} variant="secondary" onClick={() => void download('pdf')} /> : null}
        {sourceAvailable ? (
          <Collapsible trigger={TAILORING_COPY.advanced} defaultIsOpen={false}>
            <Button label={TAILORING_COPY.downloadLatex} variant="ghost" onClick={() => void download('tex')} />
          </Collapsible>
        ) : null}
      </HStack>
      {error ? <Banner status="error" title={error} /> : null}
    </VStack>
  );
}

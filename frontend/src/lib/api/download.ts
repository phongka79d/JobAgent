import {parseErrorBody} from './chat';

export async function downloadArtifact(
  url: string,
  filename: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method: 'GET',
    headers: {Accept: 'application/octet-stream'},
    signal,
  });
  if (!response.ok) throw parseErrorBody(response.status, await response.text());
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function safeArtifactName(
  label: string,
  extension: 'pdf' | 'tex',
): string {
  const base = label
    .normalize('NFKC')
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'tailored-cv';
  return `${base}.${extension}`;
}

import {afterEach, describe, expect, it, vi} from 'vitest';

import {downloadArtifact, safeArtifactName} from '../lib/api/download';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('artifact downloads', () => {
  it('downloads through a bounded blob URL without changing location', async () => {
    const click = vi.fn();
    const remove = vi.fn();
    const anchor = {click, remove, rel: '', href: '', download: ''};
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Blob(['x']), {status: 200})));
    vi.stubGlobal('URL', {...URL, createObjectURL: vi.fn().mockReturnValue('blob:test'), revokeObjectURL: vi.fn()});
    vi.spyOn(document, 'createElement').mockReturnValue(anchor as unknown as HTMLAnchorElement);
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
    const before = window.location.href;

    await downloadArtifact('http://api.test/pdf', 'resume.pdf');

    expect(click).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledOnce();
    expect(anchor.download).toBe('resume.pdf');
    expect(window.location.href).toBe(before);
  });

  it('normalizes and bounds artifact filenames', () => {
    expect(safeArtifactName('  Résumé / Candidate  ', 'pdf')).toBe('R-sum-Candidate.pdf');
    expect(safeArtifactName('***', 'tex')).toBe('tailored-cv.tex');
    expect(safeArtifactName('a'.repeat(100), 'pdf')).toHaveLength(84);
  });
});

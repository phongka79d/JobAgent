export const TAILORING_COPY = {
  noChangeAi: 'AI found no source-supported changes to apply.',
  noChangeManual: 'There are no changes to save.',
  previewPdf: 'Preview PDF',
  downloadPdf: 'Download PDF',
  downloadLatex: 'Download LaTeX source',
  advanced: 'Advanced',
  pdfDownloadError: 'The PDF could not be downloaded.',
  latexDownloadError: 'The LaTeX source could not be downloaded.',
  issueReasons: {
    not_in_source: 'This value is not supported by the selected source.',
    belongs_to_another_section: 'This source belongs to another section.',
    structure_changed: 'The source-owned structure changed.',
    required_source_missing: 'Required source evidence is missing.',
    unsupported_value: 'This value is outside the supported content bounds.',
  },
} as const;

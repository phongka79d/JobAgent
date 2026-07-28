import type {CompactMatchResult} from './matchResult';
import type {SavedJobListItem} from './types';

export const JOB_COPY = {
  savedJob: 'Saved job',
  whyThisScore: 'Why this score',
  notEnoughExperience: 'Not enough CV/JD information to score experience.',
  incompleteConfidence: 'Confidence is reduced because the CV or JD extraction is incomplete.',
  unavailable: 'Not available from the extracted information.',
} as const;

export function savedJobDisplayLabel(item: SavedJobListItem): string {
  return item.display_label.trim() || JOB_COPY.savedJob;
}

export function matchDisplayLabel(result: CompactMatchResult): string {
  if (result.displayLabel?.trim()) return result.displayLabel.trim();
  const title = result.title?.trim();
  const company = result.company?.trim();
  if (title && company) return `${title} · ${company}`;
  return title || company || JOB_COPY.savedJob;
}


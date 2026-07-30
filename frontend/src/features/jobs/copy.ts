import type {CompactMatchResult} from './matchResult';
import type {SavedJobListItem} from './types';

export const JOB_COPY = {
  savedJob: 'Saved job',
  extractionHeading: 'Job information',
  savedJobsEyebrow: 'Saved jobs',
  actions: 'Saved job actions',
  deleteJob: 'Delete job',
  deleteJobTitle: (label: string) => `Delete saved job ${label}?`,
  overviewTab: 'Job overview',
  sourceTab: 'Source text',
  whyThisScore: 'Why this score',
  matchScore: 'Match score',
  scoreExplanation: 'See “Why this score” for the source-supported skill explanation.',
  company: 'Company',
  role: 'Role',
  location: 'Location',
  workMode: 'Work mode',
  source: 'Source',
  matchedSkills: 'Matched skills',
  relatedSkills: 'Related skills',
  missingSkills: 'Missing skills',
  noSkills: 'None',
  workModes: {
    remote: 'Remote',
    hybrid: 'Hybrid',
    onsite: 'On-site',
    unknown: 'Unknown',
  },
  overallMatch: (score: string) => `Overall match: ${score}`,
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

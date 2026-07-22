/**
 * Focused observability tab identity and rail configuration (Plan 10 / Master §15.2).
 * Owns tab order and labels so oversized types.ts / TabList do not accumulate config.
 */

import type {IconName} from '@astryxdesign/core/Icon';

export type ObservabilityTabId =
  | 'overview'
  | 'cv-history'
  | 'chunks'
  | 'graph'
  | 'runs'
  | 'saved-jobs';

export type ObservabilityTabDefinition = {
  id: ObservabilityTabId;
  label: string;
  icon: IconName;
};

/**
 * Vertical rail order: Overview → CV Manager → LLM chunks → Neo4j graph →
 * Agent runs → JD đã lưu (Master §15.2).
 */
export const OBSERVABILITY_TABS: ReadonlyArray<ObservabilityTabDefinition> = [
  {id: 'overview', label: 'Overview', icon: 'info'},
  {id: 'cv-history', label: 'CV Manager', icon: 'clock'},
  {id: 'chunks', label: 'LLM chunks', icon: 'viewColumns'},
  {id: 'graph', label: 'Neo4j graph', icon: 'arrowsUpDown'},
  {id: 'runs', label: 'Agent runs', icon: 'wrench'},
  {id: 'saved-jobs', label: 'JD đã lưu', icon: 'copy'},
] as const;


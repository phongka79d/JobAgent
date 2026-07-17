/**
 * Compatibility re-export: CV History panel replaced by CV Manager (Plan 9 / 07B).
 * Prefer importing CvManagerPanel directly.
 */

export {
  CvManagerPanel as CvHistoryPanel,
  type CvManagerPanelProps as CvHistoryPanelProps,
  canDeleteCv,
} from './CvManagerPanel';

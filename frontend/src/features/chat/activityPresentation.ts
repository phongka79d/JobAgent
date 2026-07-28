import type {ClientRun} from './model';

const LABELS: Record<string, string> = {
  create_tailored_cv: 'Creating a tailored CV',
  match_jobs: 'Checking job matches',
  save_job: 'Saving this job',
  read_active_cv: 'Checking CV information',
};

export function activityLabel(technicalName: string | null, label: string): string {
  return (technicalName && LABELS[technicalName]) || label || 'Checking your request';
}

export function activityStateLabel(state: ClientRun['state']): string {
  switch (state) {
    case 'completed': return 'Complete';
    case 'failed': return 'Could not complete';
    case 'interrupted': return 'Interrupted';
    case 'running': return 'In progress';
    default: return 'Waiting';
  }
}

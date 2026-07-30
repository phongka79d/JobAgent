import type {ClientAgentActivity} from './model';
import {CHAT_COPY} from './copy';

const LABELS: Record<string, string> = {
  create_tailored_cv: CHAT_COPY.creatingTailoredCv,
  match_jobs: CHAT_COPY.checkingJobMatches,
  save_job: CHAT_COPY.savingJob,
  read_active_cv: CHAT_COPY.checkingCvInformation,
};

export function activityLabel(technicalName: string | null, label: string): string {
  return (technicalName && LABELS[technicalName]) || label || CHAT_COPY.checkingRequest;
}

export function activityStateLabel(state: ClientAgentActivity['state']): string {
  switch (state) {
    case 'pending': return CHAT_COPY.waiting;
    case 'completed': return CHAT_COPY.complete;
    case 'failed': return CHAT_COPY.couldNotComplete;
    case 'running': return CHAT_COPY.inProgress;
  }
}

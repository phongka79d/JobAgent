import type {TailoringSessionSummary} from './types';

export function sessionDisplayLabel(session: TailoringSessionSummary): string {
  const label = session.job_label;
  if (label?.display_label?.trim()) return label.display_label.trim();
  const title = label?.title?.trim();
  const company = label?.company?.trim();
  if (title && company) return `${title} · ${company}`;
  if (title || company) return title || company || 'Untitled tailored CV';
  if (session.instruction.trim()) return session.instruction.trim().slice(0, 100);
  const day = new Intl.DateTimeFormat('en-CA', {
    dateStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(session.created_at));
  return `Untitled tailored CV · ${day}`;
}


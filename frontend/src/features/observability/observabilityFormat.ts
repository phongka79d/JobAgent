const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function formatObservabilityDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date);
}

export function formatDurationMs(value: number): string {
  if (value < 1000) {
    return `${value} ms`;
  }
  if (value >= 60000) {
    const minutes = value / 60000;
    return `${Number.isInteger(minutes) ? minutes.toFixed(0) : minutes.toFixed(1)} min`;
  }
  const seconds = value / 1000;
  return `${Number.isInteger(seconds) ? seconds.toFixed(0) : seconds.toFixed(1)} s`;
}

export function formatRunDuration(
  createdAt: string,
  completedAt: string | null,
): string | null {
  if (completedAt === null) {
    return null;
  }
  const start = new Date(createdAt).getTime();
  const end = new Date(completedAt).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return null;
  }
  return formatDurationMs(end - start);
}

export type CursorPageQuery = {
  limit?: number;
  before?: string | null;
};

export function buildCursorQuery(
  query: CursorPageQuery = {},
): string {
  const params = new URLSearchParams();
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit));
  }
  if (query.before) {
    params.set('before', query.before);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

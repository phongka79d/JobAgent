import {readFileSync, readdirSync, statSync} from 'node:fs';
import {join, normalize} from 'node:path';
import {describe, expect, it} from 'vitest';

const src = join(process.cwd(), 'src');
const retainedPresentationUuidPrefixFallback =
  /(?:[A-Za-z][A-Za-z ]{0,80}\s*[:#-]?\s*)?\$\{[^}]*\b(?:[A-Za-z_$][\w$]*id|id)\b[^}]*\.(?:slice|substring)\(\s*0\s*,\s*8\s*\)/i;

function sourceFiles(path: string): string[] {
  return readdirSync(path).flatMap((name) => {
    const entry = join(path, name);
    if (statSync(entry).isDirectory()) return sourceFiles(entry);
    return /\.(?:ts|tsx)$/.test(entry) ? [entry] : [];
  });
}

function readSourceTree(paths: readonly string[], excludes: readonly string[] = []): string {
  const excluded = new Set(excludes.map(normalize));
  return paths
    .flatMap((path) => sourceFiles(join(src, path)))
    .filter((path) => !excluded.has(normalize(path)))
    .map((path) => readFileSync(path, 'utf8'))
    .join('\n');
}

describe('retained product source', () => {
  it('does not expose technical navigation, UUID fallbacks, or duplicate state owners', () => {
    const retained = readSourceTree([
      'app', 'features/profile', 'features/navigation', 'features/cv-manager',
      'features/jobs', 'features/cv-tailoring', 'features/chat',
    ]);
    for (const forbidden of [
      'LLM ' + 'chunks',
      'Neo4j ' + 'graph',
      'Agent ' + 'runs',
    ]) {
      expect(retained).not.toContain(forbidden);
    }
    expect(retained).not.toMatch(retainedPresentationUuidPrefixFallback);
    expect(retained).not.toMatch(
      /Xoá JD|Thông tin JD|Thao tác JD|Danh sách|Nguồn từ CV|Mở CV gốc|Lưu JD|Không lưu|Chưa có kết quả đánh giá/,
    );
    expect(retained).not.toMatch(/vi-VN|\btrang\b/);

    const nonAppOwners = readSourceTree([
      'features/profile', 'features/navigation', 'features/cv-manager',
      'features/jobs', 'features/cv-tailoring', 'features/chat',
    ], [
      join(src, 'features', 'jobs', 'savedJobsState.ts'),
      join(src, 'features', 'cv-tailoring', 'state.ts'),
    ]);
    expect(nonAppOwners).not.toMatch(/useSavedJobsState\(/);
    expect(nonAppOwners).not.toMatch(/useCvTailoringState\(/);
  });

  it('rejects retained UUID-prefix presentation fallbacks for jobs and other labels', () => {
    expect('Job ${job.id.slice(0, 8)}').toMatch(retainedPresentationUuidPrefixFallback);
    expect('JD ${jobId.slice(0, 8)}').toMatch(retainedPresentationUuidPrefixFallback);
    expect('Saved job ${id.slice(0, 8)}').toMatch(retainedPresentationUuidPrefixFallback);
    expect('Saved job: ${savedJobId.substring(0, 8)}').toMatch(retainedPresentationUuidPrefixFallback);
  });
});

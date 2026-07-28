import {readFileSync, readdirSync, statSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {describe, expect, it} from 'vitest';

import {PRODUCT_DESTINATIONS} from '../features/navigation/productNavigation';

const sourceRoot = fileURLToPath(new URL('../features', import.meta.url));

function frontendSourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = `${directory}/${name}`;
    return statSync(path).isDirectory()
      ? frontendSourceFiles(path)
      : /\.(?:ts|tsx|css)$/.test(path)
        ? [path]
        : [];
  });
}

describe('product navigation', () => {
  it('defines the three product destinations in their product order', () => {
    expect(PRODUCT_DESTINATIONS.map(({id, label}) => [id, label])).toEqual([
      ['overview', 'Overview'],
      ['saved-jobs', 'Saved Jobs'],
      ['tailored-cvs', 'Tailored CVs'],
    ]);
  });

  it('removes technical observability labels and modules from retained source', () => {
    const source = frontendSourceFiles(sourceRoot)
      .map((file) => readFileSync(file, 'utf8'))
      .join('\n');
    expect(source).not.toContain('LLM chunks');
    expect(source).not.toContain('Neo4j graph');
    expect(source).not.toContain('Agent runs');
    expect(source).not.toContain('features/observability');
  });

  it('keeps saved-job and CV-tailoring controller ownership in App', () => {
    const app = readFileSync(
      fileURLToPath(new URL('../app/App.tsx', import.meta.url)),
      'utf8',
    );
    const controllerDefinitions = new Set([
      fileURLToPath(
        new URL('../features/jobs/savedJobsState.ts', import.meta.url),
      ),
      fileURLToPath(
        new URL('../features/cv-tailoring/state.ts', import.meta.url),
      ),
    ]);
    const featureSource = frontendSourceFiles(
      fileURLToPath(new URL('../features', import.meta.url)),
    )
      .filter((file) => !controllerDefinitions.has(file))
      .map((file) => readFileSync(file, 'utf8'))
      .join('\n');

    expect(app.split('useSavedJobsState(')).toHaveLength(2);
    expect(app.split('useCvTailoringState(')).toHaveLength(2);
    expect(featureSource).not.toContain('useSavedJobsState(');
    expect(featureSource).not.toContain('useCvTailoringState(');
  });
});

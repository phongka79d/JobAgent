import {describe, expect, it} from 'vitest';

import {toGraphModel} from '../features/observability/graphPresentation';
import {graphReady} from './support/observability';

describe('graph presentation mapping', () => {
  it('namespaces and sorts bounded nodes and resolves directed edges', () => {
    const model = toGraphModel(graphReady());
    expect(model.nodes.map((node) => node.key)).toEqual([
      'candidate:cand-1',
      'job:job-1',
      'skill:python',
    ]);
    expect(model.links).toEqual([
      expect.objectContaining({
        key: 'HAS_SKILL:candidate:cand-1->skill:python',
        source: 'candidate:cand-1',
        target: 'skill:python',
        type: 'HAS_SKILL',
      }),
    ]);
  });

  it('drops an inconsistent edge instead of crashing the graph', () => {
    const snapshot = graphReady();
    snapshot.edges.push({
      source_id: 'missing',
      target_id: 'python',
      type: 'REQUIRES',
    });
    expect(toGraphModel(snapshot).links).toHaveLength(1);
  });

  it('maps only display metadata without mutating the API snapshot', () => {
    const snapshot = graphReady();
    const original = structuredClone(snapshot);

    const model = toGraphModel(snapshot);

    expect(snapshot).toEqual(original);
    expect(model.nodes).toEqual([
      expect.objectContaining({
        key: 'candidate:cand-1',
        rawId: 'cand-1',
        kind: 'candidate',
        label: 'Candidate',
        metadata: [
          ['ID', 'cand-1'],
          ['Revision', 'r1'],
        ],
      }),
      expect.objectContaining({
        key: 'job:job-1',
        rawId: 'job-1',
        kind: 'job',
        label: 'Engineer',
        metadata: [
          ['ID', 'job-1'],
          ['Title', 'Engineer'],
          ['Company', 'Acme'],
          ['Revision', 'j1'],
        ],
      }),
      expect.objectContaining({
        key: 'skill:python',
        rawId: 'python',
        kind: 'skill',
        label: 'python',
        metadata: [['Canonical name', 'python']],
      }),
    ]);
  });

  it('derives the same identity from identical reordered contents', () => {
    const snapshot = graphReady();
    snapshot.jobs.push({
      id: 'job-2',
      title: 'Analyst',
      company: 'Beta',
      revision: 'j2',
    });
    snapshot.skills.push({canonical_name: 'sql'});
    snapshot.edges.push({
      source_id: 'job-2',
      target_id: 'sql',
      type: 'REQUIRES',
    });
    const reordered = structuredClone(snapshot);
    reordered.jobs.reverse();
    reordered.skills.reverse();
    reordered.edges.reverse();

    expect(toGraphModel(reordered).identity).toBe(toGraphModel(snapshot).identity);
  });
});

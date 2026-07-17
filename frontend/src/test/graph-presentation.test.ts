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

  it('resolves every supported directed edge type', () => {
    const snapshot = graphReady();
    snapshot.skills.push({canonical_name: 'sql'});
    snapshot.edges.push(
      {source_id: 'job-1', target_id: 'python', type: 'REQUIRES'},
      {source_id: 'job-1', target_id: 'sql', type: 'PREFERS'},
      {source_id: 'python', target_id: 'sql', type: 'RELATED_TO'},
    );

    expect(toGraphModel(snapshot).links).toEqual([
      {
        key: 'HAS_SKILL:candidate:cand-1->skill:python',
        source: 'candidate:cand-1',
        target: 'skill:python',
        type: 'HAS_SKILL',
      },
      {
        key: 'PREFERS:job:job-1->skill:sql',
        source: 'job:job-1',
        target: 'skill:sql',
        type: 'PREFERS',
      },
      {
        key: 'RELATED_TO:skill:python->skill:sql',
        source: 'skill:python',
        target: 'skill:sql',
        type: 'RELATED_TO',
      },
      {
        key: 'REQUIRES:job:job-1->skill:python',
        source: 'job:job-1',
        target: 'skill:python',
        type: 'REQUIRES',
      },
    ]);
  });

  it('distinguishes topology identities when node keys contain delimiters', () => {
    const combined = graphReady();
    combined.candidate = null;
    combined.jobs = [];
    combined.skills = [{canonical_name: 'python|skill:sql'}];
    combined.edges = [];
    const split = structuredClone(combined);
    split.skills = [{canonical_name: 'python'}, {canonical_name: 'sql'}];

    expect(toGraphModel(combined).identity).not.toBe(
      toGraphModel(split).identity,
    );
  });

  it('keeps colliding relationship tuples as uniquely keyed links', () => {
    const snapshot = graphReady();
    snapshot.candidate = null;
    snapshot.jobs = [];
    snapshot.skills = [
      {canonical_name: 'a'},
      {canonical_name: 'b->skill:c'},
      {canonical_name: 'a->skill:b'},
      {canonical_name: 'c'},
    ];
    snapshot.edges = [
      {source_id: 'a', target_id: 'b->skill:c', type: 'RELATED_TO'},
      {source_id: 'a->skill:b', target_id: 'c', type: 'RELATED_TO'},
    ];

    const keys = toGraphModel(snapshot).links.map((link) => link.key);

    expect(keys).toHaveLength(2);
    expect(new Set(keys).size).toBe(2);
    expect(keys).toContain('RELATED_TO:skill:a->skill:b%2D%3Eskill:c');
    expect(keys).toContain('RELATED_TO:skill:a%2D%3Eskill:b->skill:c');
  });

  it('deduplicates repeated node and edge keys', () => {
    const snapshot = graphReady();
    snapshot.jobs.push(structuredClone(snapshot.jobs[0]));
    snapshot.skills.push(structuredClone(snapshot.skills[0]));
    snapshot.edges.push(structuredClone(snapshot.edges[0]));

    const model = toGraphModel(snapshot);

    expect(model.nodes.map((node) => node.key)).toEqual([
      'candidate:cand-1',
      'job:job-1',
      'skill:python',
    ]);
    expect(model.links.map((link) => link.key)).toEqual([
      'HAS_SKILL:candidate:cand-1->skill:python',
    ]);
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

  it('preserves exact ordering and identity for frozen permuted contents', () => {
    const snapshot = graphReady();
    snapshot.jobs.push({
      id: 'job-2',
      title: 'Analyst',
      company: 'Beta',
      revision: 'j2',
    });
    snapshot.skills.push({canonical_name: 'sql'});
    snapshot.edges.push(
      {source_id: 'job-1', target_id: 'python', type: 'REQUIRES'},
      {source_id: 'job-2', target_id: 'sql', type: 'PREFERS'},
      {source_id: 'python', target_id: 'sql', type: 'RELATED_TO'},
    );
    const original = structuredClone(snapshot);
    const reordered = structuredClone(snapshot);
    reordered.jobs.reverse();
    reordered.skills.reverse();
    reordered.edges.reverse();

    if (snapshot.candidate) Object.freeze(snapshot.candidate);
    snapshot.jobs.forEach((job) => Object.freeze(job));
    snapshot.skills.forEach((skill) => Object.freeze(skill));
    snapshot.edges.forEach((edge) => Object.freeze(edge));
    Object.freeze(snapshot.jobs);
    Object.freeze(snapshot.skills);
    Object.freeze(snapshot.edges);
    Object.freeze(snapshot);

    const model = toGraphModel(snapshot);
    const reorderedModel = toGraphModel(reordered);

    expect(snapshot).toEqual(original);
    expect(model.nodes.map((node) => node.key)).toEqual([
      'candidate:cand-1',
      'job:job-1',
      'job:job-2',
      'skill:python',
      'skill:sql',
    ]);
    expect(reorderedModel.nodes.map((node) => node.key)).toEqual(
      model.nodes.map((node) => node.key),
    );
    expect(model.links.map((link) => link.key)).toEqual([
      'HAS_SKILL:candidate:cand-1->skill:python',
      'PREFERS:job:job-2->skill:sql',
      'RELATED_TO:skill:python->skill:sql',
      'REQUIRES:job:job-1->skill:python',
    ]);
    expect(reorderedModel.links.map((link) => link.key)).toEqual(
      model.links.map((link) => link.key),
    );
    expect(reorderedModel.identity).toBe(model.identity);
  });
});

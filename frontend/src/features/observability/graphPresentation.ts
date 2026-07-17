import type {SimulationLinkDatum, SimulationNodeDatum} from 'd3-force';

import type {GraphEdgeType, GraphSnapshot} from './types';

export type GraphNodeKind = 'candidate' | 'job' | 'skill';

export type GraphNodeDatum = SimulationNodeDatum & {
  key: string;
  rawId: string;
  kind: GraphNodeKind;
  label: string;
  metadata: ReadonlyArray<readonly [label: string, value: string]>;
};

export type GraphLinkDatum = SimulationLinkDatum<GraphNodeDatum> & {
  key: string;
  type: GraphEdgeType;
  source: string | GraphNodeDatum;
  target: string | GraphNodeDatum;
};

export type GraphModel = {
  identity: string;
  nodes: GraphNodeDatum[];
  links: GraphLinkDatum[];
};

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function sourceKey(type: GraphEdgeType, id: string): string {
  if (type === 'HAS_SKILL') return `candidate:${id}`;
  if (type === 'REQUIRES' || type === 'PREFERS') return `job:${id}`;
  return `skill:${id}`;
}

function targetKey(id: string): string {
  return `skill:${id}`;
}

export function toGraphModel(snapshot: GraphSnapshot): GraphModel {
  const nodes: GraphNodeDatum[] = [];

  if (snapshot.candidate) {
    nodes.push({
      key: `candidate:${snapshot.candidate.id}`,
      rawId: snapshot.candidate.id,
      kind: 'candidate',
      label: 'Candidate',
      metadata: [
        ['ID', snapshot.candidate.id],
        ['Revision', snapshot.candidate.revision],
      ],
    });
  }

  nodes.push(
    ...snapshot.jobs.map(
      (job): GraphNodeDatum => ({
        key: `job:${job.id}`,
        rawId: job.id,
        kind: 'job',
        label: job.title || job.id,
        metadata: [
          ['ID', job.id],
          ['Title', job.title],
          ['Company', job.company],
          ['Revision', job.revision],
        ],
      }),
    ),
    ...snapshot.skills.map(
      (skill): GraphNodeDatum => ({
        key: `skill:${skill.canonical_name}`,
        rawId: skill.canonical_name,
        kind: 'skill',
        label: skill.canonical_name,
        metadata: [['Canonical name', skill.canonical_name]],
      }),
    ),
  );

  nodes.sort((left, right) =>
    compareStrings(`${left.kind}:${left.key}`, `${right.kind}:${right.key}`),
  );
  const nodeKeys = new Set(nodes.map((node) => node.key));

  const links = snapshot.edges
    .flatMap((edge): GraphLinkDatum[] => {
      const source = sourceKey(edge.type, edge.source_id);
      const target = targetKey(edge.target_id);
      if (!nodeKeys.has(source) || !nodeKeys.has(target)) return [];
      return [
        {
          key: `${edge.type}:${source}->${target}`,
          source,
          target,
          type: edge.type,
        },
      ];
    })
    .sort((left, right) =>
      compareStrings(
        `${left.type}:${left.source}:${left.target}`,
        `${right.type}:${right.source}:${right.target}`,
      ),
    );

  return {
    identity: [...nodes.map((node) => node.key), ...links.map((link) => link.key)].join('|'),
    nodes,
    links,
  };
}

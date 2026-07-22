import type {SimulationLinkDatum, SimulationNodeDatum} from 'd3-force';

import type {GraphEdgeType, GraphSnapshot} from './types';

export type GraphNodeKind =
  | 'candidate'
  | 'job'
  | 'skill'
  | 'cv'
  | 'cv_section'
  | 'cv_entry';

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

function uniqueByKey<T extends {key: string}>(items: T[]): T[] {
  const unique = new Map<string, T>();
  for (const item of items) {
    // ponytail: Keep the first duplicate key; handle conflicts only if contracts permit them.
    if (!unique.has(item.key)) unique.set(item.key, item);
  }
  return [...unique.values()];
}

function sourceKey(type: GraphEdgeType, id: string): string {
  if (type === 'HAS_SKILL' || type === 'PROJECTS_TO') return `candidate:${id}`;
  if (type === 'REQUIRES' || type === 'PREFERS') return `job:${id}`;
  if (type === 'HAS_SECTION') return `cv:${id}`;
  if (type === 'HAS_ENTRY') return `cv_section:${id}`;
  return `skill:${id}`;
}

function targetKey(type: GraphEdgeType, id: string): string {
  if (type === 'PROJECTS_TO') return `cv:${id}`;
  if (type === 'HAS_SECTION') return `cv_section:${id}`;
  if (type === 'HAS_ENTRY') return `cv_entry:${id}`;
  return `skill:${id}`;
}

function escapeLinkEndpoint(key: string): string {
  return key.replaceAll('%', '%25').replaceAll('->', '%2D%3E');
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

  if (snapshot.cv) {
    nodes.push({
      key: `cv:${snapshot.cv.id}`,
      rawId: snapshot.cv.id,
      kind: 'cv',
      label: snapshot.cv.original_name || 'Active CV',
      metadata: [
        ['ID', snapshot.cv.id],
        ['Name', snapshot.cv.original_name],
        ['Extraction version', snapshot.cv.extraction_version],
        ['Revision', snapshot.cv.revision],
      ],
    });
  }

  for (const section of snapshot.sections ?? []) {
    nodes.push({
      key: `cv_section:${section.id}`,
      rawId: section.id,
      kind: 'cv_section',
      label: section.heading || section.id,
      metadata: [
        ['ID', section.id],
        ['Heading', section.heading],
        ['Kind', section.kind],
        ['Ordinal', String(section.ordinal)],
        ['Entries', String(section.entry_count)],
      ],
    });
  }

  for (const entry of snapshot.entries ?? []) {
    nodes.push({
      key: `cv_entry:${entry.id}`,
      rawId: entry.id,
      kind: 'cv_entry',
      label: entry.title || entry.preview || entry.id,
      metadata: [
        ['ID', entry.id],
        ['Section', entry.section_id],
        ['Ordinal', String(entry.ordinal)],
        ['Title', entry.title ?? ''],
        ['Subtitle', entry.subtitle ?? ''],
        ['Date', entry.date_text ?? ''],
        ['Preview', entry.preview],
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
      (skill): GraphNodeDatum => {
        const metadata: Array<readonly [string, string]> = [
          ['Canonical key', skill.canonical_key],
        ];
        if (skill.category) metadata.push(['Category', skill.category]);
        return {
          key: `skill:${skill.canonical_key}`,
          rawId: skill.canonical_key,
          kind: 'skill',
          label: skill.display_name,
          metadata,
        };
      },
    ),
  );

  const uniqueNodes = uniqueByKey(nodes).sort((left, right) =>
    compareStrings(`${left.kind}:${left.key}`, `${right.kind}:${right.key}`),
  );
  const nodeKeys = new Set(uniqueNodes.map((node) => node.key));

  const links = uniqueByKey(
    snapshot.edges.flatMap((edge): GraphLinkDatum[] => {
      const source = sourceKey(edge.type, edge.source_id);
      const target = targetKey(edge.type, edge.target_id);
      if (!nodeKeys.has(source) || !nodeKeys.has(target)) return [];
      const escapedSource = escapeLinkEndpoint(source);
      const escapedTarget = escapeLinkEndpoint(target);
      return [
        {
          key: `${edge.type}:${escapedSource}->${escapedTarget}`,
          source,
          target,
          type: edge.type,
        },
      ];
    }),
  ).sort((left, right) => compareStrings(left.key, right.key));

  return {
    identity: JSON.stringify([
      uniqueNodes.map((node) => node.key),
      links.map((link) => link.key),
    ]),
    nodes: uniqueNodes,
    links,
  };
}

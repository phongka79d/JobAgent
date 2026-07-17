import type {GraphLinkDatum} from './graphPresentation';

const PARALLEL_EDGE_GAP = 12;
const PARALLEL_LABEL_GAP = 80;

export type GraphEdgeOffset = {
  edge: number;
  label: number;
};

function endpointKey(endpoint: GraphLinkDatum['source']): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.key;
}

export function getParallelEdgeOffsets(
  links: GraphLinkDatum[],
): Map<string, GraphEdgeOffset> {
  const groups = new Map<string, GraphLinkDatum[]>();
  for (const link of links) {
    const groupKey = `${endpointKey(link.source)}\u0000${endpointKey(link.target)}`;
    const group = groups.get(groupKey);
    if (group) group.push(link);
    else groups.set(groupKey, [link]);
  }

  const offsets = new Map<string, GraphEdgeOffset>();
  for (const group of groups.values()) {
    const ordered = [...group].sort((left, right) =>
      left.key < right.key ? -1 : left.key > right.key ? 1 : 0,
    );
    ordered.forEach((link, index) => {
      const centeredIndex = index - (ordered.length - 1) / 2;
      offsets.set(link.key, {
        edge: centeredIndex * PARALLEL_EDGE_GAP,
        label: centeredIndex * PARALLEL_LABEL_GAP,
      });
    });
  }
  return offsets;
}

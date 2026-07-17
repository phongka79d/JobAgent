export const GRAPH_NODE_RADIUS = 24;
export const GRAPH_NODE_LABEL_Y = GRAPH_NODE_RADIUS + 14;

const GRAPH_NODE_LABEL_MAX_LENGTH = 18;
const GRAPH_NODE_LABEL_CHAR_WIDTH = 7;
const GRAPH_NODE_LABEL_HALF_HEIGHT = 10;

type PositionedGraphNode = {
  x?: number;
  y?: number;
  label?: string;
};

export type GraphNodeRenderedExtent = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export function formatGraphNodeLabel(label: string): string {
  return label.length > GRAPH_NODE_LABEL_MAX_LENGTH
    ? `${label.slice(0, GRAPH_NODE_LABEL_MAX_LENGTH - 3)}...`
    : label;
}

export function getGraphNodeRenderedExtent(
  node: PositionedGraphNode & {x: number; y: number},
): GraphNodeRenderedExtent {
  const visibleLabel = formatGraphNodeLabel(node.label ?? '');
  const labelHalfWidth =
    (visibleLabel.length * GRAPH_NODE_LABEL_CHAR_WIDTH) / 2;
  const halfWidth = Math.max(GRAPH_NODE_RADIUS, labelHalfWidth);
  const labelBottom = visibleLabel
    ? GRAPH_NODE_LABEL_Y + GRAPH_NODE_LABEL_HALF_HEIGHT
    : GRAPH_NODE_RADIUS;

  return {
    left: node.x - halfWidth,
    right: node.x + halfWidth,
    top: node.y - GRAPH_NODE_RADIUS,
    bottom: node.y + labelBottom,
  };
}

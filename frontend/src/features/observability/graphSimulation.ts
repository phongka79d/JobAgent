import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
} from 'd3-force';

import type {
  GraphLinkDatum,
  GraphModel,
  GraphNodeDatum,
} from './graphPresentation';

export type GraphSimulationController = {
  nodes: GraphNodeDatum[];
  links: GraphLinkDatum[];
  resize: (width: number, height: number) => void;
  beginDrag: (key: string) => void;
  dragNode: (key: string, x: number, y: number) => void;
  endDrag: () => void;
  cancelDrag: () => void;
  resetLayout: () => void;
  stop: () => void;
};

export type GraphSimulationOptions = {
  reducedMotion?: boolean;
};

export function createGraphSimulation(
  model: GraphModel,
  width: number,
  height: number,
  onTick: () => void,
  options: GraphSimulationOptions = {},
): GraphSimulationController {
  const nodes = model.nodes.map((node) => ({...node}));
  const links = model.links.map((link) => ({
    ...link,
    source: typeof link.source === 'string' ? link.source : link.source.key,
    target: typeof link.target === 'string' ? link.target : link.target.key,
  }));
  const nodesByKey = new Map(nodes.map((node) => [node.key, node]));
  let activeDragKey: string | null = null;
  const reducedMotion = options.reducedMotion === true;
  const simulation = forceSimulation(nodes)
    .force(
      'link',
      forceLink<GraphNodeDatum, GraphLinkDatum>(links)
        .id((node) => node.key)
        .distance(96)
        .strength(0.7),
    )
    .force('charge', forceManyBody().strength(-260))
    .force(
      'collision',
      forceCollide<GraphNodeDatum>().radius(38).strength(0.9),
    )
    .force('center', forceCenter(width / 2, height / 2))
    .on('tick', onTick);

  if (reducedMotion) {
    simulation.stop();
    simulation.tick(120);
    onTick();
  }

  return {
    nodes,
    links,
    resize(nextWidth, nextHeight) {
      simulation.force(
        'center',
        forceCenter(nextWidth / 2, nextHeight / 2),
      );
      if (reducedMotion) {
        simulation.stop();
        simulation.alpha(1).tick(120);
        onTick();
      } else {
        simulation.alpha(0.3).restart();
      }
    },
    beginDrag(key) {
      if (!nodesByKey.has(key)) return;
      activeDragKey = key;
      simulation.alphaTarget(0.3);
      if (!reducedMotion) simulation.restart();
    },
    dragNode(key, x, y) {
      const node = nodesByKey.get(key);
      if (!node) return;
      node.x = x;
      node.y = y;
      node.fx = x;
      node.fy = y;
      if (reducedMotion) onTick();
    },
    endDrag() {
      activeDragKey = null;
      simulation.alphaTarget(0);
      if (reducedMotion) simulation.stop();
    },
    cancelDrag() {
      const node = activeDragKey ? nodesByKey.get(activeDragKey) : null;
      if (node) {
        node.fx = null;
        node.fy = null;
      }
      activeDragKey = null;
      simulation.alphaTarget(0);
      if (reducedMotion) {
        simulation.stop();
        onTick();
      } else {
        simulation.alpha(0.3).restart();
      }
    },
    resetLayout() {
      activeDragKey = null;
      for (const node of nodes) {
        node.fx = null;
        node.fy = null;
      }
      simulation.alpha(1);
      if (reducedMotion) {
        simulation.stop();
        simulation.tick(120);
        onTick();
      } else {
        simulation.restart();
      }
    },
    stop() {
      simulation.stop();
    },
  };
}

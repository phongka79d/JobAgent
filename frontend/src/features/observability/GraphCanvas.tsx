import {Button} from '@astryxdesign/core/Button';
import {HStack} from '@astryxdesign/core/HStack';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from 'react';

import type {
  GraphLinkDatum,
  GraphModel,
  GraphNodeDatum,
} from './graphPresentation';
import {getParallelEdgeOffsets} from './graphEdgeLayout';
import {
  formatGraphNodeLabel,
  GRAPH_NODE_LABEL_Y,
  GRAPH_NODE_RADIUS,
} from './graphNodeRendering';
import {useGraphSimulation} from './useGraphSimulation';
import {useGraphViewport} from './useGraphViewport';

type GraphCanvasProps = {
  model: GraphModel;
};

type GraphEdgeViewProps = {
  link: GraphLinkDatum;
  markerId: string;
  offset: number;
  labelOffset: number;
};

function GraphEdgeView({link, markerId, offset, labelOffset}: GraphEdgeViewProps) {
  const source = typeof link.source === 'string' ? null : link.source;
  const target = typeof link.target === 'string' ? null : link.target;
  const sourceX = source?.x ?? 0;
  const sourceY = source?.y ?? 0;
  const targetX = target?.x ?? 0;
  const targetY = target?.y ?? 0;
  const deltaX = targetX - sourceX;
  const deltaY = targetY - sourceY;
  const distance = Math.hypot(deltaX, deltaY) || 1;
  const unitX = deltaX / distance;
  const unitY = deltaY / distance;
  const normalX = -unitY;
  const normalY = unitX;
  const startX = sourceX + unitX * GRAPH_NODE_RADIUS + normalX * offset;
  const startY = sourceY + unitY * GRAPH_NODE_RADIUS + normalY * offset;
  const endX = targetX - unitX * (GRAPH_NODE_RADIUS + 4) + normalX * offset;
  const endY = targetY - unitY * (GRAPH_NODE_RADIUS + 4) + normalY * offset;
  const labelX = (sourceX + targetX) / 2 + normalX * labelOffset;
  const labelY = (sourceY + targetY) / 2 + normalY * labelOffset;
  const labelWidth = link.type.length * 7 + 12;

  return (
    <g className="jobagent-graph-edge-view">
      <line
        className="jobagent-graph-edge"
        x1={startX}
        y1={startY}
        x2={endX}
        y2={endY}
        markerEnd={`url(#${markerId})`}
      />
      <g
        className="jobagent-graph-edge-label"
        transform={`translate(${labelX} ${labelY})`}
      >
        <rect x={-labelWidth / 2} y={-10} width={labelWidth} height={20} />
        <text>{link.type}</text>
      </g>
    </g>
  );
}

type GraphNodeViewProps = {
  node: GraphNodeDatum;
  isSelected: boolean;
  onSelect: (node: GraphNodeDatum) => void;
  onDragStart: (key: string) => void;
  onDrag: (key: string, clientX: number, clientY: number) => void;
  onDragEnd: () => void;
  onDragCancel: () => void;
};

function GraphNodeView({
  node,
  isSelected,
  onSelect,
  onDragStart,
  onDrag,
  onDragEnd,
  onDragCancel,
}: GraphNodeViewProps) {
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const visibleLabel = formatGraphNodeLabel(node.label);

  function handleKeyDown(event: KeyboardEvent<SVGGElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onSelect(node);
  }

  function handlePointerDown(event: PointerEvent<SVGGElement>) {
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    onDragStart(node.key);
  }

  function handlePointerMove(event: PointerEvent<SVGGElement>) {
    if (!event.currentTarget.hasPointerCapture?.(event.pointerId)) return;
    onDrag(node.key, event.clientX, event.clientY);
  }

  function releasePointer(event: PointerEvent<SVGGElement>) {
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
  }

  function handlePointerEnd(event: PointerEvent<SVGGElement>) {
    releasePointer(event);
    onDragEnd();
  }

  function handlePointerCancel(event: PointerEvent<SVGGElement>) {
    releasePointer(event);
    onDragCancel();
  }

  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={`${node.kind} ${node.label} (${node.rawId})`}
      aria-pressed={isSelected}
      className={`jobagent-graph-node jobagent-graph-node--${node.kind}${isSelected ? ' is-selected' : ''}`}
      transform={`translate(${x} ${y})`}
      data-graph-node=""
      data-testid={`jobagent-graph-node-${node.key}`}
      onClick={() => onSelect(node)}
      onFocus={() => onSelect(node)}
      onKeyDown={handleKeyDown}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerCancel}
    >
      <circle r={GRAPH_NODE_RADIUS} />
      <text className="jobagent-graph-node-label" y={GRAPH_NODE_LABEL_Y}>
        {visibleLabel}
      </text>
    </g>
  );
}

function GraphCanvasInner({model}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const arrowMarkerId = useId().replaceAll(':', '');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [viewportNodes, setViewportNodes] = useState(model.nodes);
  const {size, transform, fitView, toGraphPoint} = useGraphViewport(
    containerRef,
    svgRef,
    viewportNodes,
    model.identity,
  );
  const {controller} = useGraphSimulation(model, size.width, size.height);
  const nodes = controller?.nodes ?? model.nodes;
  const links = controller?.links ?? model.links;
  const edgeOffsets = useMemo(() => getParallelEdgeOffsets(links), [links]);
  const selectedNode = nodes.find((node) => node.key === selectedKey) ?? null;

  useEffect(() => {
    if (controller) setViewportNodes(controller.nodes);
  }, [controller]);

  function dragNode(key: string, clientX: number, clientY: number) {
    const [x, y] = toGraphPoint(clientX, clientY);
    controller?.dragNode(key, x, y);
  }

  return (
    <VStack gap={2} width="100%">
      <HStack gap={1} hAlign="end" vAlign="center">
        <Button label="Fit view" variant="ghost" size="sm" onClick={fitView} />
        <Button
          label="Reset layout"
          variant="ghost"
          size="sm"
          onClick={() => controller?.resetLayout()}
        />
      </HStack>

      <div ref={containerRef} className="jobagent-graph-canvas">
        <svg
          ref={svgRef}
          role="group"
          aria-label="Candidate, jobs and skills network"
          className="jobagent-graph-svg"
          viewBox={`0 0 ${size.width} ${size.height}`}
        >
          <defs>
            <marker
              id={arrowMarkerId}
              markerWidth="8"
              markerHeight="8"
              refX="7"
              refY="4"
              orient="auto"
            >
              <path d="M0,0 L8,4 L0,8 Z" className="jobagent-graph-arrow" />
            </marker>
          </defs>
          <g transform={transform.toString()}>
            {links.map((link) => (
              <GraphEdgeView
                key={link.key}
                link={link}
                markerId={arrowMarkerId}
                offset={edgeOffsets.get(link.key)?.edge ?? 0}
                labelOffset={edgeOffsets.get(link.key)?.label ?? 0}
              />
            ))}
            {nodes.map((node) => (
              <GraphNodeView
                key={node.key}
                node={node}
                isSelected={node.key === selectedKey}
                onSelect={(selected) => setSelectedKey(selected.key)}
                onDragStart={(key) => controller?.beginDrag(key)}
                onDrag={dragNode}
                onDragEnd={() => controller?.endDrag()}
                onDragCancel={() => controller?.cancelDrag()}
              />
            ))}
          </g>
        </svg>
      </div>

      <HStack
        gap={2}
        vAlign="center"
        className="jobagent-graph-legend"
        aria-label="Graph node legend"
      >
        {(
          [
            ['candidate', 'Candidate'],
            ['job', 'Job'],
            ['skill', 'Skill'],
            ['cv', 'CV'],
            ['cv_section', 'Section'],
            ['cv_entry', 'Entry'],
          ] as const
        ).map(([kind, label]) => (
          <span
            key={kind}
            className={`jobagent-graph-legend-item jobagent-graph-legend-item--${kind}`}
          >
            <span aria-hidden="true" />
            {label}
          </span>
        ))}
      </HStack>

      {selectedNode ? (
        <section data-testid="jobagent-graph-selected-metadata">
          <Text type="label">Selected node</Text>
          <MetadataList columns="single" label={{position: 'start'}}>
            {selectedNode.metadata.map(([label, value]) => (
              <MetadataListItem key={label} label={label}>
                {value || 'Not provided'}
              </MetadataListItem>
            ))}
          </MetadataList>
        </section>
      ) : null}
    </VStack>
  );
}

export function GraphCanvas({model}: GraphCanvasProps) {
  return <GraphCanvasInner key={model.identity} model={model} />;
}

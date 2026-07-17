import {select} from 'd3-selection';
import {
  zoom,
  zoomIdentity,
  type ZoomBehavior,
  type ZoomTransform,
} from 'd3-zoom';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from 'react';

export type GraphViewportSize = {
  width: number;
  height: number;
};

export type GraphViewport = {
  size: GraphViewportSize;
  transform: ZoomTransform;
  fitView: () => void;
  toGraphPoint: (clientX: number, clientY: number) => [number, number];
};

export function calculateFitTransform(
  nodes: ReadonlyArray<{x?: number; y?: number}>,
  size: GraphViewportSize,
  padding = 40,
) {
  const points = nodes.filter(
    (node): node is {x: number; y: number} =>
      typeof node.x === 'number' &&
      Number.isFinite(node.x) &&
      typeof node.y === 'number' &&
      Number.isFinite(node.y),
  );
  if (points.length === 0) return zoomIdentity;
  const minX = Math.min(...points.map((node) => node.x));
  const maxX = Math.max(...points.map((node) => node.x));
  const minY = Math.min(...points.map((node) => node.y));
  const maxY = Math.max(...points.map((node) => node.y));
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const scale = Math.min(
    4,
    Math.max(
      0.25,
      Math.min(
        Math.max(1, size.width - padding * 2) / spanX,
        Math.max(1, size.height - padding * 2) / spanY,
      ),
    ),
  );
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  return zoomIdentity
    .translate(
      size.width / 2 - centerX * scale,
      size.height / 2 - centerY * scale,
    )
    .scale(scale);
}

export function useGraphViewport(
  containerRef: RefObject<HTMLElement | null>,
  svgRef: RefObject<SVGSVGElement | null>,
  nodes: ReadonlyArray<{x?: number; y?: number}>,
  identity: string,
): GraphViewport {
  const [size, setSize] = useState<GraphViewportSize>({width: 0, height: 0});
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  const behaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const fittedIdentityRef = useRef<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setSize((current) =>
        current.width === rect.width && current.height === rect.height
          ? current
          : {width: rect.width, height: rect.height},
      );
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const behavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.25, 4])
      .filter((event) => {
        const target = event.target;
        return !(
          target instanceof Element && target.closest('[data-graph-node]')
        );
      })
      .on('zoom.jobagent', (event) => setTransform(event.transform));
    const selection = select(svg);
    behaviorRef.current = behavior;
    selection.call(behavior);

    return () => {
      selection.on('.zoom', null);
      behavior.on('zoom.jobagent', null);
      if (behaviorRef.current === behavior) behaviorRef.current = null;
    };
  }, [svgRef]);

  const fitView = useCallback(() => {
    const svg = svgRef.current;
    const behavior = behaviorRef.current;
    if (!svg || !behavior) return;
    select(svg).call(behavior.transform, calculateFitTransform(nodes, size));
  }, [nodes, size, svgRef]);

  useEffect(() => {
    if (
      fittedIdentityRef.current === identity ||
      nodes.length === 0 ||
      size.width <= 0 ||
      size.height <= 0 ||
      !svgRef.current ||
      !behaviorRef.current ||
      !nodes.every(
        (node) =>
          typeof node.x === 'number' &&
          Number.isFinite(node.x) &&
          typeof node.y === 'number' &&
          Number.isFinite(node.y),
      )
    ) {
      return;
    }
    fittedIdentityRef.current = identity;
    fitView();
  });

  const toGraphPoint = useCallback(
    (clientX: number, clientY: number): [number, number] => {
      const rect = svgRef.current?.getBoundingClientRect();
      return transform.invert([
        clientX - (rect?.left ?? 0),
        clientY - (rect?.top ?? 0),
      ]);
    },
    [svgRef, transform],
  );

  return {size, transform, fitView, toGraphPoint};
}

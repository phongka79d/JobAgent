import {act, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  calculateFitTransform,
  useGraphViewport,
} from '../features/observability/useGraphViewport';

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

function createViewportElements() {
  const container = document.createElement('div');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 600 400');
  Object.defineProperty(svg, 'viewBox', {
    value: {baseVal: {x: 0, y: 0, width: 600, height: 400}},
  });
  container.getBoundingClientRect = () =>
    ({width: 600, height: 400, left: 0, top: 0}) as DOMRect;
  svg.getBoundingClientRect = () =>
    ({width: 600, height: 400, left: 10, top: 20}) as DOMRect;
  container.append(svg);
  document.body.append(container);
  return {
    container,
    svg,
    containerRef: {current: container},
    svgRef: {current: svg},
  };
}

function dragViewport(target: Element, options: MouseEventInit = {}) {
  const view = target.ownerDocument.defaultView;
  const down = new globalThis.MouseEvent('mousedown', {
    bubbles: true,
    clientX: 20,
    clientY: 30,
    ...options,
  });
  const move = new globalThis.MouseEvent('mousemove', {
    bubbles: true,
    clientX: 60,
    clientY: 70,
  });
  const up = new globalThis.MouseEvent('mouseup', {bubbles: true});
  for (const event of [down, move, up]) {
    Object.defineProperty(event, 'view', {value: view});
  }
  act(() => {
    target.dispatchEvent(down);
    window.dispatchEvent(move);
    window.dispatchEvent(up);
  });
}

function installInstrumentedResizeObserver() {
  let callback: ResizeObserverCallback | null = null;
  const observe = vi.fn();
  const disconnect = vi.fn();
  class InstrumentedResizeObserver {
    constructor(nextCallback: ResizeObserverCallback) {
      callback = nextCallback;
    }
    observe = observe;
    unobserve = vi.fn();
    disconnect = disconnect;
  }
  vi.stubGlobal('ResizeObserver', InstrumentedResizeObserver);
  return {
    observe,
    disconnect,
    notify(target: Element, contentRect: DOMRect) {
      if (!callback) throw new Error('ResizeObserver was not constructed');
      callback(
        [{target, contentRect} as ResizeObserverEntry],
        {} as ResizeObserver,
      );
    },
  };
}

describe('graph viewport fitting', () => {
  it('calculates a bounded fit transform around positioned nodes', () => {
    const transform = calculateFitTransform(
      [{x: 0, y: 0}, {x: 200, y: 100}],
      {width: 600, height: 400},
      40,
    );
    expect(transform.k).toBeGreaterThan(0);
    expect(transform.k).toBeLessThanOrEqual(4);
    expect(transform.apply([100, 50])).toEqual([300, 200]);
  });

  it('keeps sparse node circles and external labels inside the fit viewport', () => {
    const nodes = [
      {x: 100, y: 200, label: 'Principal Engineer'},
      {x: 120, y: 200, label: 'Distributed Systems'},
    ];
    const transform = calculateFitTransform(nodes, {width: 300, height: 200});
    const renderedExtents = nodes.map((node) => ({
      left: node.x - 63,
      right: node.x + 63,
      top: node.y - 24,
      bottom: node.y + 48,
    }));

    expect(transform.k).toBeGreaterThan(1);
    expect(transform.k).toBeLessThan(4);
    for (const extent of renderedExtents) {
      expect(transform.applyX(extent.left)).toBeGreaterThanOrEqual(40 - 1e-9);
      expect(transform.applyX(extent.right)).toBeLessThanOrEqual(260 + 1e-9);
      expect(transform.applyY(extent.top)).toBeGreaterThanOrEqual(40 - 1e-9);
      expect(transform.applyY(extent.bottom)).toBeLessThanOrEqual(160 + 1e-9);
    }
  });

  it('ignores unpositioned nodes and keeps the minimum fit scale bounded', () => {
    const transform = calculateFitTransform(
      [{x: Number.NaN, y: 10}, {}, {x: 0, y: 0}, {x: 10_000, y: 10_000}],
      {width: 100, height: 100},
    );

    expect(transform.k).toBe(0.25);
  });

  it('composes canvas exclusion with D3 default mouse protections', () => {
    const {svg, containerRef, svgRef} = createViewportElements();
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    node.setAttribute('data-graph-node', 'true');
    svg.append(node);
    const {result} = renderHook(() =>
      useGraphViewport(containerRef, svgRef, [], 'graph-a'),
    );

    for (const options of [{button: 2}, {button: 1}, {button: 0, ctrlKey: true}]) {
      dragViewport(svg, options);
      expect(result.current.transform.toString()).toBe('translate(0,0) scale(1)');
    }

    dragViewport(svg, {button: 0});
    expect(result.current.transform.toString()).not.toBe(
      'translate(0,0) scale(1)',
    );
    const canvasTransform = result.current.transform.toString();
    dragViewport(node, {button: 0});
    expect(result.current.transform.toString()).toBe(canvasTransform);
    act(() => {
      node.dispatchEvent(
        new globalThis.WheelEvent('wheel', {bubbles: true, deltaY: -100}),
      );
    });
    expect(result.current.transform.toString()).toBe(canvasTransform);
  });

  it('observes size, auto-fits finite nodes once per identity, and inverts coordinates', () => {
    const observer = installInstrumentedResizeObserver();
    const {container, containerRef, svgRef} = createViewportElements();
    const {result, rerender} = renderHook(
      ({nodes, identity}) =>
        useGraphViewport(containerRef, svgRef, nodes, identity),
      {initialProps: {nodes: [{}], identity: 'graph-a'}},
    );
    const contentRect = container.getBoundingClientRect();

    act(() => observer.notify(container, contentRect));

    expect(observer.observe).toHaveBeenCalledWith(container);
    expect(result.current.size).toEqual({width: 600, height: 400});
    expect(result.current.transform.toString()).toBe('translate(0,0) scale(1)');

    rerender({nodes: [{x: 0, y: 0}, {x: 200, y: 100}], identity: 'graph-a'});
    const firstFit = result.current.transform;
    expect(firstFit.k).toBeCloseTo(520 / (200 + 48));
    expect(
      result.current.toGraphPoint(
        firstFit.applyX(100) + 10,
        firstFit.applyY(50) + 20,
      ),
    ).toEqual([100, 50]);

    rerender({nodes: [{x: 0, y: 0}, {x: 20, y: 20}], identity: 'graph-a'});
    expect(result.current.transform.toString()).toBe(firstFit.toString());

    rerender({nodes: [{x: 0, y: 0}, {x: 20, y: 20}], identity: 'graph-b'});
    expect(result.current.transform.k).toBe(4);
  });

  it('disconnects resize and removes active zoom listeners on cleanup', () => {
    const observer = installInstrumentedResizeObserver();
    const {svg, containerRef, svgRef} = createViewportElements();
    const {result, unmount} = renderHook(() =>
      useGraphViewport(containerRef, svgRef, [], 'graph-a'),
    );

    dragViewport(svg);
    const attachedTransform = result.current.transform.toString();
    expect(attachedTransform).not.toBe('translate(0,0) scale(1)');

    unmount();
    dragViewport(svg);

    expect(observer.disconnect).toHaveBeenCalledOnce();
    expect((svg as SVGSVGElement & {__zoom: {toString(): string}}).__zoom.toString()).toBe(
      attachedTransform,
    );
  });

  it('ignores fit requests while viewport dimensions are invalid', () => {
    const observer = installInstrumentedResizeObserver();
    const {container, containerRef, svgRef} = createViewportElements();
    const nodes = [{x: 0, y: 0}, {x: 200, y: 100}];
    const {result} = renderHook(() =>
      useGraphViewport(containerRef, svgRef, nodes, 'graph-a'),
    );
    const invalidRect = {
      ...container.getBoundingClientRect(),
      width: Number.NaN,
    } as DOMRect;

    act(() => observer.notify(container, invalidRect));
    act(() => result.current.fitView());

    expect(result.current.transform.toString()).toBe('translate(0,0) scale(1)');
  });
});

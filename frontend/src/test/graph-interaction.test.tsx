import {act, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {toGraphModel} from '../features/observability/graphPresentation';
import {
  createGraphSimulation,
  type GraphSimulationController,
} from '../features/observability/graphSimulation';
import {
  useGraphSimulation,
  type GraphSimulationFactory,
} from '../features/observability/useGraphSimulation';
import {calculateFitTransform} from '../features/observability/useGraphViewport';
import {
  graphReady,
  installMatchMedia,
} from './support/observability';

afterEach(() => {
  installMatchMedia(false);
});

describe('graph simulation controller', () => {
  it('pins a dragged node, keeps it pinned on drop, and releases all pins on reset', () => {
    const controller = createGraphSimulation(
      toGraphModel(graphReady()),
      640,
      420,
      vi.fn(),
    );
    controller.beginDrag('candidate:cand-1');
    controller.dragNode('candidate:cand-1', 120, 140);
    controller.endDrag();
    expect(controller.nodes[0]).toMatchObject({fx: 120, fy: 140});
    controller.resetLayout();
    expect(
      controller.nodes.every((node) => node.fx == null && node.fy == null),
    ).toBe(true);
    controller.stop();
  });

  it('clones model data and preserves pinned coordinates through resize', () => {
    const model = toGraphModel(graphReady());
    const original = structuredClone(model);
    const controller = createGraphSimulation(model, 640, 420, vi.fn(), {
      reducedMotion: true,
    });

    controller.dragNode('candidate:cand-1', 80, 90);
    controller.resize(800, 500);

    expect(model).toEqual(original);
    expect(controller.nodes).not.toBe(model.nodes);
    expect(controller.links).not.toBe(model.links);
    expect(controller.nodes[0]).toMatchObject({fx: 80, fy: 90});
    controller.stop();
  });

  it('settles synchronously when reduced motion is requested', () => {
    const onTick = vi.fn();
    const controller = createGraphSimulation(
      toGraphModel(graphReady()),
      640,
      420,
      onTick,
      {reducedMotion: true},
    );
    expect(
      controller.nodes.every(
        (node) =>
          typeof node.x === 'number' &&
          Number.isFinite(node.x) &&
          typeof node.y === 'number' &&
          Number.isFinite(node.y),
      ),
    ).toBe(true);
    expect(onTick).toHaveBeenCalledOnce();
    controller.stop();
  });
});

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

  it('ignores unpositioned nodes and keeps the minimum fit scale bounded', () => {
    const transform = calculateFitTransform(
      [{x: Number.NaN, y: 10}, {}, {x: 0, y: 0}, {x: 10_000, y: 10_000}],
      {width: 100, height: 100},
    );

    expect(transform.k).toBe(0.25);
  });
});

describe('graph simulation hook lifecycle', () => {
  it('reuses the controller across resize, recreates it for identity changes, and cleans up', () => {
    installMatchMedia(true);
    const controllers: GraphSimulationController[] = [];
    const factory = vi.fn<GraphSimulationFactory>((model) => {
      const controller: GraphSimulationController = {
        nodes: model.nodes.map((node) => ({...node})),
        links: model.links.map((link) => ({...link})),
        resize: vi.fn(),
        beginDrag: vi.fn(),
        dragNode: vi.fn(),
        endDrag: vi.fn(),
        resetLayout: vi.fn(),
        stop: vi.fn(),
      };
      controllers.push(controller);
      return controller;
    });
    const firstModel = toGraphModel(graphReady());
    const {result, rerender, unmount} = renderHook(
      ({model, width, height}) =>
        useGraphSimulation(model, width, height, factory),
      {initialProps: {model: firstModel, width: 640, height: 420}},
    );

    expect(factory).toHaveBeenCalledOnce();
    expect(factory.mock.calls[0][4]).toEqual({reducedMotion: true});
    expect(result.current.controller).toBe(controllers[0]);

    act(() => factory.mock.calls[0][3]());
    expect(result.current.revision).toBe(1);

    rerender({model: {...firstModel}, width: 800, height: 500});
    expect(factory).toHaveBeenCalledOnce();
    expect(controllers[0].resize).toHaveBeenCalledWith(800, 500);

    const changedSnapshot = graphReady();
    changedSnapshot.skills.push({canonical_name: 'sql'});
    const secondModel = toGraphModel(changedSnapshot);
    rerender({model: secondModel, width: 800, height: 500});

    expect(factory).toHaveBeenCalledTimes(2);
    expect(controllers[0].stop).toHaveBeenCalledOnce();
    expect(result.current.controller).toBe(controllers[1]);

    unmount();
    expect(controllers[1].stop).toHaveBeenCalledOnce();
  });
});

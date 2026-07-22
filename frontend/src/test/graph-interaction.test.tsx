import {act, cleanup, renderHook} from '@testing-library/react';
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
import {
  graphReady,
  installMatchMedia,
} from './support/observability';

const activeControllers = new Set<GraphSimulationController>();

afterEach(() => {
  cleanup();
  for (const controller of activeControllers) controller.stop();
  activeControllers.clear();
  installMatchMedia(false);
});

describe('graph simulation controller', () => {
  it('pre-settles normal-motion nodes around the viewport before first render', () => {
    const controller = createGraphSimulation(
      toGraphModel(graphReady()),
      260,
      432,
      vi.fn(),
    );
    activeControllers.add(controller);
    const center = controller.nodes.reduce(
      (sum, node) => ({
        x: sum.x + (node.x ?? 0),
        y: sum.y + (node.y ?? 0),
      }),
      {x: 0, y: 0},
    );

    expect(center.x / controller.nodes.length).toBeCloseTo(130, 0);
    expect(center.y / controller.nodes.length).toBeCloseTo(216, 0);
  });

  it('pins a dragged node, keeps it pinned on drop, and releases all pins on reset', () => {
    const controller = createGraphSimulation(
      toGraphModel(graphReady()),
      640,
      420,
      vi.fn(),
    );
    activeControllers.add(controller);
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
    activeControllers.add(controller);

    controller.dragNode('candidate:cand-1', 80, 90);
    controller.resize(800, 500);

    expect(model).toEqual(original);
    expect(controller.nodes).not.toBe(model.nodes);
    expect(controller.links).not.toBe(model.links);
    expect(controller.nodes[0]).toMatchObject({fx: 80, fy: 90});
    controller.stop();
  });

  it('releases the active node when a drag is canceled', () => {
    const controller = createGraphSimulation(
      toGraphModel(graphReady()),
      640,
      420,
      vi.fn(),
      {reducedMotion: true},
    );
    activeControllers.add(controller);

    controller.beginDrag('candidate:cand-1');
    controller.dragNode('candidate:cand-1', 120, 140);
    controller.cancelDrag();

    expect(controller.nodes[0].fx).toBeNull();
    expect(controller.nodes[0].fy).toBeNull();
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
    activeControllers.add(controller);
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

  it('resolves object link endpoints onto cloned simulation nodes', () => {
    const model = toGraphModel(graphReady());
    const source = model.nodes.find((node) => node.key === 'candidate:cand-1');
    const target = model.nodes.find((node) => node.key === 'skill:python');
    if (!source || !target) throw new Error('Expected graph fixture nodes');
    model.links[0].source = source;
    model.links[0].target = target;

    const controller = createGraphSimulation(model, 640, 420, vi.fn(), {
      reducedMotion: true,
    });
    activeControllers.add(controller);

    expect(controller.links[0].source).toBe(
      controller.nodes.find((node) => node.key === source.key),
    );
    expect(controller.links[0].target).toBe(
      controller.nodes.find((node) => node.key === target.key),
    );
    expect(controller.links[0].source).not.toBe(source);
    expect(controller.links[0].target).not.toBe(target);
  });
});

describe('graph simulation hook lifecycle', () => {
  it('settles an invalid initial controller on its first valid resize', () => {
    const resize = vi.fn();
    const factory = vi.fn<GraphSimulationFactory>((model) => ({
      nodes: model.nodes.map((node) => ({...node})),
      links: model.links.map((link) => ({...link})),
      resize,
      beginDrag: vi.fn(),
      dragNode: vi.fn(),
      endDrag: vi.fn(),
      cancelDrag: vi.fn(),
      resetLayout: vi.fn(),
      stop: vi.fn(),
    }));
    const model = toGraphModel(graphReady());
    const {rerender, unmount} = renderHook(
      ({width, height}) =>
        useGraphSimulation(model, width, height, factory),
      {initialProps: {width: 0, height: 0}},
    );

    expect(factory).toHaveBeenCalledOnce();

    rerender({width: 260, height: 432});
    expect(resize).toHaveBeenCalledWith(260, 432, true);
    unmount();
  });

  it('syncs presentation fields without recreating or moving the controller', () => {
    const factory = vi.fn<GraphSimulationFactory>((model) => ({
      nodes: model.nodes.map((node, index) => ({
        ...node,
        x: 20 + index,
        y: 30 + index,
        fx: index === 0 ? 20 : null,
        fy: index === 0 ? 30 : null,
      })),
      links: model.links.map((link) => ({...link})),
      resize: vi.fn(),
      beginDrag: vi.fn(),
      dragNode: vi.fn(),
      endDrag: vi.fn(),
      cancelDrag: vi.fn(),
      resetLayout: vi.fn(),
      stop: vi.fn(),
    }));
    const firstModel = toGraphModel(graphReady());
    const {result, rerender} = renderHook(
      ({model}) => useGraphSimulation(model, 640, 420, factory),
      {initialProps: {model: firstModel}},
    );
    const controller = result.current.controller;
    const position = {
      x: controller?.nodes[0].x,
      y: controller?.nodes[0].y,
      fx: controller?.nodes[0].fx,
      fy: controller?.nodes[0].fy,
    };
    const updatedModel = {
      ...firstModel,
      nodes: firstModel.nodes.map((node, index) =>
        index === 0
          ? {
              ...node,
              rawId: 'updated-id',
              kind: 'job' as const,
              label: 'Updated candidate',
              metadata: [['Revision', 'updated']] as const,
            }
          : node,
      ),
    };

    rerender({model: updatedModel});

    expect(factory).toHaveBeenCalledOnce();
    expect(result.current.controller).toBe(controller);
    expect(result.current.controller?.nodes[0]).toMatchObject({
      rawId: 'updated-id',
      kind: 'job',
      label: 'Updated candidate',
      metadata: [['Revision', 'updated']],
      ...position,
    });
    const revision = result.current.revision;
    rerender({
      model: {
        ...updatedModel,
        nodes: updatedModel.nodes.map((node) => ({
          ...node,
          metadata: node.metadata.map(
            ([label, value]) => [label, value] as const,
          ),
        })),
      },
    });
    expect(result.current.revision).toBe(revision);
  });

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
        cancelDrag: vi.fn(),
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
    changedSnapshot.skills.push({
      canonical_name: 'sql',
      canonical_key: 'sql',
      display_name: 'SQL',
      category: 'language',
    });
    const secondModel = toGraphModel(changedSnapshot);
    rerender({model: secondModel, width: 800, height: 500});

    expect(factory).toHaveBeenCalledTimes(2);
    expect(controllers[0].stop).toHaveBeenCalledOnce();
    expect(result.current.controller).toBe(controllers[1]);

    unmount();
    expect(controllers[1].stop).toHaveBeenCalledOnce();
  });
});

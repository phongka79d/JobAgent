import {useEffect, useRef, useState} from 'react';

import type {GraphModel} from './graphPresentation';
import {
  createGraphSimulation,
  type GraphSimulationController,
  type GraphSimulationOptions,
} from './graphSimulation';

export type GraphSimulationFactory = (
  model: GraphModel,
  width: number,
  height: number,
  onTick: () => void,
  options?: GraphSimulationOptions,
) => GraphSimulationController;

export type GraphSimulationResult = {
  controller: GraphSimulationController | null;
  revision: number;
};

export function useGraphSimulation(
  model: GraphModel,
  width: number,
  height: number,
  factory: GraphSimulationFactory = createGraphSimulation,
): GraphSimulationResult {
  const [controllerState, setControllerState] = useState<{
    identity: string;
    controller: GraphSimulationController;
  } | null>(null);
  const [revision, setRevision] = useState(0);
  const sizeRef = useRef<{
    controller: GraphSimulationController;
    width: number;
    height: number;
  } | null>(null);
  const identity = model.identity;

  useEffect(() => {
    let active = true;
    const controller = factory(
      model,
      width,
      height,
      () => {
        if (active) setRevision((current) => current + 1);
      },
      {
        reducedMotion: window.matchMedia(
          '(prefers-reduced-motion: reduce)',
        ).matches,
      },
    );
    sizeRef.current = {controller, width, height};
    setControllerState({identity, controller});

    return () => {
      active = false;
      controller.stop();
    };
  }, [factory, identity]);

  const controller =
    controllerState?.identity === identity
      ? controllerState.controller
      : null;

  useEffect(() => {
    if (!controller) return;
    const modelNodes = new Map(model.nodes.map((node) => [node.key, node]));
    let changed = false;
    for (const node of controller.nodes) {
      const modelNode = modelNodes.get(node.key);
      if (!modelNode) continue;
      if (
        node.rawId !== modelNode.rawId ||
        node.kind !== modelNode.kind ||
        node.label !== modelNode.label ||
        node.metadata.length !== modelNode.metadata.length ||
        node.metadata.some(
          ([label, value], index) =>
            label !== modelNode.metadata[index]?.[0] ||
            value !== modelNode.metadata[index]?.[1],
        )
      ) {
        node.rawId = modelNode.rawId;
        node.kind = modelNode.kind;
        node.label = modelNode.label;
        node.metadata = modelNode.metadata;
        changed = true;
      }
    }
    if (changed) setRevision((current) => current + 1);
  }, [controller, model]);

  useEffect(() => {
    if (!controller) return;
    const currentSize = sizeRef.current;
    if (
      currentSize?.controller === controller &&
      currentSize.width === width &&
      currentSize.height === height
    ) {
      return;
    }
    controller.resize(width, height);
    sizeRef.current = {controller, width, height};
  }, [controller, height, width]);

  return {controller, revision};
}

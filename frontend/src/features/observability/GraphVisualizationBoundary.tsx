import {Banner} from '@astryxdesign/core/Banner';
import {Component, type ReactNode} from 'react';

type GraphVisualizationBoundaryProps = {
  children: ReactNode;
  resetKey: unknown;
};

type GraphVisualizationBoundaryState = {
  failed: boolean;
  resetKey: unknown;
};

export class GraphVisualizationBoundary extends Component<
  GraphVisualizationBoundaryProps,
  GraphVisualizationBoundaryState
> {
  state: GraphVisualizationBoundaryState = {
    failed: false,
    resetKey: this.props.resetKey,
  };

  static getDerivedStateFromProps(
    props: GraphVisualizationBoundaryProps,
    state: GraphVisualizationBoundaryState,
  ): GraphVisualizationBoundaryState | null {
    return state.resetKey === props.resetKey
      ? null
      : {failed: false, resetKey: props.resetKey};
  }

  static getDerivedStateFromError(): Partial<GraphVisualizationBoundaryState> {
    return {failed: true};
  }

  render() {
    if (this.state.failed) {
      return (
        <Banner
          status="error"
          title="Graph visualization unavailable"
          description="The semantic graph data remains available below."
          container="section"
          data-testid="jobagent-graph-visualization-error"
        />
      );
    }
    return this.props.children;
  }
}

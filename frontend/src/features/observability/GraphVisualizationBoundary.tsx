import {Banner} from '@astryxdesign/core/Banner';
import {Component, type ReactNode} from 'react';

type GraphVisualizationBoundaryProps = {
  children: ReactNode;
};

type GraphVisualizationBoundaryState = {
  failed: boolean;
};

export class GraphVisualizationBoundary extends Component<
  GraphVisualizationBoundaryProps,
  GraphVisualizationBoundaryState
> {
  state: GraphVisualizationBoundaryState = {failed: false};

  static getDerivedStateFromError(): GraphVisualizationBoundaryState {
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

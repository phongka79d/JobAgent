import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl';
import {VStack} from '@astryxdesign/core/VStack';
import {useState} from 'react';

import type {CachedResource as JobResource} from '../jobs/savedJobsState';
import type {SelectedJobSkillMap} from '../jobs/types';
import {ObservabilityPanelHeader} from './ObservabilityPanelHeader';
import {SkillCompatibilityMap} from './SkillCompatibilityMap';
import type {CachedResource as GraphResource} from './state';
import {TechnicalGraphPanel} from './TechnicalGraphPanel';
import type {GraphSnapshot} from './types';

type GraphViewMode = 'compatibility' | 'technical';

export type GraphPanelProps = {
  resource: GraphResource<GraphSnapshot>;
  onRefresh: () => void;
  selectedJobId?: string | null;
  skillMapResource?: JobResource<SelectedJobSkillMap> | null;
  onRefreshSkillMap?: () => void;
};

export function GraphPanel({
  resource,
  onRefresh,
  selectedJobId = null,
  skillMapResource = null,
  onRefreshSkillMap,
}: GraphPanelProps) {
  const [mode, setMode] = useState<GraphViewMode>('compatibility');
  const compatibilityMode = mode === 'compatibility';
  const mapRefreshing = skillMapResource?.phase === 'loading';

  return (
    <section
      className="jobagent-obs-panel"
      data-testid="jobagent-obs-graph"
      role="tabpanel"
      id="jobagent-obs-panel-graph"
      aria-labelledby="jobagent-obs-tab-graph"
    >
      <ObservabilityPanelHeader
        eyebrow={compatibilityMode ? 'Độ phù hợp kỹ năng' : 'Graph projection'}
        title={compatibilityMode ? 'Bản đồ CV–JD' : 'Neo4j graph'}
        onRefresh={
          compatibilityMode ? (onRefreshSkillMap ?? onRefresh) : onRefresh
        }
        isRefreshing={
          compatibilityMode ? Boolean(mapRefreshing) : resource.phase === 'loading'
        }
        refreshTestId="jobagent-obs-graph-refresh"
      />
      <VStack gap={3} width="100%">
        <SegmentedControl
          value={mode}
          onChange={(value) => {
            if (value === 'compatibility' || value === 'technical') {
              setMode(value);
            }
          }}
          label="Chế độ xem bản đồ kỹ năng"
          size="sm"
          layout="fill"
        >
          <SegmentedControlItem value="compatibility" label="Phù hợp CV–JD" />
          <SegmentedControlItem value="technical" label="Kỹ thuật" />
        </SegmentedControl>

        {compatibilityMode ? (
          <SkillCompatibilityMap
            selectedJobId={selectedJobId}
            resource={skillMapResource}
          />
        ) : (
          <TechnicalGraphPanel resource={resource} />
        )}
      </VStack>
    </section>
  );
}

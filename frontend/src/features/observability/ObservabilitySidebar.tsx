/**
 * Observability inspector composition: tabs, lazy fetch/cache, and panel routing.
 * Profile/upload state stays in CvSidebar; this owns inspector state only.
 */

import {useEffect, type ReactNode} from 'react';
import {useSideNavCollapse} from '@astryxdesign/core/SideNav';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';

import type {ObservabilityApi} from './api';
import {ChunkPanel} from './ChunkPanel';
import {CvHistoryPanel} from './CvHistoryPanel';
import {GraphPanel} from './GraphPanel';
import {ObservabilityTabList} from './ObservabilityTabList';
import {RunHistoryPanel} from './RunHistoryPanel';
import {useObservabilityState} from './state';
import type {CvHistoryItem, ObservabilityTabId} from './types';

import './observability.css';

export type ObservabilitySidebarProps = {
  /** Overview content owned by CvSidebar (upload/profile). */
  overview: ReactNode;
  /** Compact status shown when the sidenav is collapsed. */
  collapsedStatus: {
    label: string;
    variant: 'success' | 'neutral' | 'warning' | 'error';
    cvName: string | null;
  };
  observability: ReturnType<typeof useObservabilityState>;
};

export function ObservabilityStateBoundary({
  api,
  children,
}: {
  api?: Partial<ObservabilityApi>;
  children: (
    observability: ReturnType<typeof useObservabilityState>,
  ) => ReactNode;
}) {
  const observability = useObservabilityState({api});
  return children(observability);
}

export function ObservabilitySidebar({
  overview,
  collapsedStatus,
  observability: obs,
}: ObservabilitySidebarProps) {
  const {isCollapsed, toggle} = useSideNavCollapse();
  const {state} = obs;

  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    if (state.selectedTab === 'cv-history') {
      void obs.loadCvHistory({signal});
    } else if (state.selectedTab === 'runs') {
      void obs.loadRuns({signal});
    } else if (state.selectedTab === 'graph') {
      void obs.loadGraph({signal});
    } else if (
      state.selectedTab === 'chunks' &&
      state.selectedAttachmentId
    ) {
      void obs.loadChunkList(state.selectedAttachmentId, {signal});
    }
    return () => {
      controller.abort();
    };
    // load* functions are stable and skip cached resources.
  }, [state.selectedTab, state.selectedAttachmentId]);

  const handleSelectTab = (tab: ObservabilityTabId) => {
    obs.selectTab(tab);
    if (isCollapsed) {
      toggle();
    }
  };

  const handleSelectAttachment = (item: CvHistoryItem) => {
    obs.selectAttachment(item.id);
  };

  const handleOpenFile = (item: CvHistoryItem) => {
    obs.openRetainedFile(item.id, item.file_available);
  };

  const chunkList = state.selectedAttachmentId
    ? state.chunkLists[state.selectedAttachmentId] ?? null
    : null;

  if (isCollapsed) {
    return (
      <div
        className="jobagent-obs-root"
        data-collapsed="true"
        data-testid="jobagent-obs-root"
      >
        <ObservabilityTabList
          value={state.selectedTab}
          isCollapsed
          onChange={handleSelectTab}
        />
        <div
          className="jobagent-obs-collapsed-status"
          data-testid="jobagent-obs-collapsed-status"
        >
          <StatusDot
            variant={collapsedStatus.variant}
            label={collapsedStatus.label}
          />
          <Text type="supporting" maxLines={2}>
            {collapsedStatus.label}
          </Text>
          <Text type="supporting" maxLines={2}>
            {collapsedStatus.cvName ?? 'No CV'}
          </Text>
        </div>
      </div>
    );
  }

  return (
    <div
      className="jobagent-obs-root"
      data-collapsed="false"
      data-testid="jobagent-obs-root"
    >
      <div data-testid="jobagent-obs-tabs">
        <ObservabilityTabList
          value={state.selectedTab}
          isCollapsed={false}
          onChange={handleSelectTab}
        />
      </div>

      <div className="jobagent-obs-content">
        {state.selectedTab === 'overview' ? (
          <div
            role="tabpanel"
            id="jobagent-obs-panel-overview"
            aria-labelledby="jobagent-obs-tab-overview"
            data-testid="jobagent-obs-overview"
          >
            {overview}
          </div>
        ) : null}

        {state.selectedTab === 'cv-history' ? (
          <CvHistoryPanel
            resource={state.cvHistory}
            selectedAttachmentId={state.selectedAttachmentId}
            onSelect={handleSelectAttachment}
            onOpenFile={handleOpenFile}
            onRefresh={() => {
              void obs.loadCvHistory({force: true});
            }}
          />
        ) : null}

        {state.selectedTab === 'chunks' ? (
          <ChunkPanel
            selectedAttachmentId={state.selectedAttachmentId}
            listResource={chunkList}
            details={state.chunkDetails}
            expandedOrdinal={state.expandedChunkOrdinal}
            onExpand={(ordinal) => {
              if (!state.selectedAttachmentId) {
                return;
              }
              void obs.expandChunk(state.selectedAttachmentId, ordinal);
            }}
            onCollapse={obs.collapseChunk}
            onRefresh={() => {
              if (!state.selectedAttachmentId) {
                return;
              }
              void obs.loadChunkList(state.selectedAttachmentId, {force: true});
            }}
          />
        ) : null}

        {state.selectedTab === 'graph' ? (
          <GraphPanel
            resource={state.graph}
            onRefresh={() => {
              void obs.loadGraph({force: true});
            }}
          />
        ) : null}

        {state.selectedTab === 'runs' ? (
          <RunHistoryPanel
            resource={state.runs}
            expandedRunId={state.expandedRunId}
            onToggleRun={(runId) => {
              obs.setExpandedRun(
                state.expandedRunId === runId ? null : runId,
              );
            }}
            onRefresh={() => {
              void obs.loadRuns({force: true});
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

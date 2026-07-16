/**
 * Observability inspector composition: tabs, lazy fetch/cache, panel routing.
 * Profile/upload state stays in CvSidebar; this owns tab/selection/cache only.
 */

import {useEffect, type ReactNode} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Text} from '@astryxdesign/core/Text';
import {useSideNavCollapse} from '@astryxdesign/core/SideNav';
import {StatusDot} from '@astryxdesign/core/StatusDot';

import type {ObservabilityApi} from './api';
import {ChunkPanel} from './ChunkPanel';
import {CvHistoryPanel} from './CvHistoryPanel';
import {GraphPanel} from './GraphPanel';
import {RunHistoryPanel} from './RunHistoryPanel';
import {useObservabilityState} from './state';
import type {CvHistoryItem, ObservabilityTabId} from './types';

import './observability.css';

const TABS: ReadonlyArray<{id: ObservabilityTabId; label: string}> = [
  {id: 'overview', label: 'Overview'},
  {id: 'cv-history', label: 'CV history'},
  {id: 'chunks', label: 'LLM chunks'},
  {id: 'graph', label: 'Neo4j graph'},
  {id: 'runs', label: 'Agent runs'},
];

export type ObservabilitySidebarProps = {
  /** Overview content owned by CvSidebar (upload/profile). */
  overview: ReactNode;
  /** Compact status shown when the sidenav is collapsed. */
  collapsedStatus: {
    label: string;
    variant: 'success' | 'neutral' | 'warning' | 'error';
    cvName: string | null;
  };
  api?: Partial<ObservabilityApi>;
};

export function ObservabilitySidebar({
  overview,
  collapsedStatus,
  api,
}: ObservabilitySidebarProps) {
  const {isCollapsed} = useSideNavCollapse();
  const obs = useObservabilityState({api});
  const {state} = obs;

  // Lazy-load non-overview tabs on first select (or after explicit refresh).
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
    // Re-run only on tab / selected-attachment changes; load* skip when cached.
  }, [state.selectedTab, state.selectedAttachmentId]);

  if (isCollapsed) {
    return (
      <div
        className="jobagent-obs-collapsed-status"
        data-testid="jobagent-obs-collapsed-status"
      >
        <StatusDot
          variant={collapsedStatus.variant}
          label={collapsedStatus.label}
        />
        <Text type="supporting" maxLines={2}>
          {collapsedStatus.cvName ?? 'No CV'}
        </Text>
      </div>
    );
  }

  const selectTab = (tab: ObservabilityTabId) => {
    obs.selectTab(tab);
  };

  const handleSelectAttachment = (item: CvHistoryItem) => {
    obs.selectAttachment(item.id);
  };

  const handleOpenFile = (item: CvHistoryItem) => {
    obs.openRetainedFile(item.id, item.file_available);
  };

  const chunkList =
    state.selectedAttachmentId
      ? state.chunkLists[state.selectedAttachmentId] ?? null
      : null;

  return (
    <div className="jobagent-obs-root" data-testid="jobagent-obs-root">
      <div
        className="jobagent-obs-tabs"
        role="tablist"
        aria-label="Observability inspector"
        data-testid="jobagent-obs-tabs"
      >
        {TABS.map((tab) => {
          const selected = state.selectedTab === tab.id;
          return (
            <Button
              key={tab.id}
              label={tab.label}
              variant={selected ? 'primary' : 'ghost'}
              size="sm"
              className="jobagent-obs-tab"
              role="tab"
              id={`jobagent-obs-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`jobagent-obs-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => selectTab(tab.id)}
              data-testid={`jobagent-obs-tab-${tab.id}`}
            />
          );
        })}
      </div>

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
  );
}

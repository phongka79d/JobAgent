/**
 * Observability inspector composition: tabs, lazy fetch/cache, and panel routing.
 * Profile/upload state stays in CvSidebar; this owns inspector state only.
 * Saved-JD list/detail/actions compose focused jobs modules (Plan 10 / Master §15.6).
 */

import {useCallback, useEffect, useRef, type ReactNode} from 'react';
import {useSideNavCollapse} from '@astryxdesign/core/SideNav';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';

import {SavedJobsPanel} from '../jobs/SavedJobsPanel';
import {useSavedJobsState} from '../jobs/savedJobsState';
import {ChunkPanel} from './ChunkPanel';
import {CvManagerPanel} from './CvManagerPanel';
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
  /**
   * Activation / zero-result invalidation signal for sidebar-local saved-JD
   * currentness (reducer signal — not a remount key).
   */
  savedJobsInvalidateKey?: number;
  /**
   * CV Manager reprocess → App → ChatPage stream path.
   * Returns false when composition refuses (locked/duplicate).
   */
  onCvReprocess?: (attachmentId: string) => boolean;
  /** After confirmed delete success (profile summary may need refresh). */
  onCvDeleted?: () => void;
};

export function ObservabilitySidebar({
  overview,
  collapsedStatus,
  observability: obs,
  savedJobsInvalidateKey = 0,
  onCvReprocess,
  onCvDeleted,
}: ObservabilitySidebarProps) {
  const {isCollapsed, toggle} = useSideNavCollapse();
  const {state} = obs;
  const savedJobs = useSavedJobsState();
  const handledSavedJobsInvalidateKey = useRef(savedJobsInvalidateKey);

  const loadSavedJobsList = useCallback(() => {
    void savedJobs.loadList();
  }, [savedJobs.loadList]);

  const refreshSavedJobsList = useCallback(() => {
    void savedJobs.loadList({}, {force: true});
  }, [savedJobs.loadList]);

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
    // Tab/selection plus activation generation: open tabs auto-reload after
    // Save Profile without requiring a manual refresh (Plan 11 F-03).
  }, [
    state.selectedTab,
    state.selectedAttachmentId,
    state.activationGeneration,
  ]);

  useEffect(() => {
    if (state.selectedTab !== 'saved-jobs') {
      return;
    }
    const jobId = savedJobs.state.selectedJobId;
    if (!jobId) {
      return;
    }
    const controller = new AbortController();
    void savedJobs.loadDetail(jobId, {signal: controller.signal});
    return () => {
      controller.abort();
    };
    // Selection-driven detail load; loadDetail is cache-aware.
  }, [state.selectedTab, savedJobs.state.selectedJobId]);

  // Saved-JD invalidation signal: mark list/selected detail non-current; force
  // open-tab GETs; closed tab refreshes lazily on next selection/mount.
  useEffect(() => {
    if (handledSavedJobsInvalidateKey.current === savedJobsInvalidateKey) {
      return;
    }
    handledSavedJobsInvalidateKey.current = savedJobsInvalidateKey;
    const selectedJobId = savedJobs.state.selectedJobId;
    const tabOpen = state.selectedTab === 'saved-jobs';
    savedJobs.invalidateCurrentness();
    if (tabOpen) {
      void savedJobs.loadList({}, {force: true});
      if (selectedJobId) {
        void savedJobs.loadDetail(selectedJobId, {force: true});
      }
    }
    // Signal-only trigger; selection/tab captured at invalidation time (Plan 11).
  }, [savedJobsInvalidateKey]);

  // Evaluate/delete success bumps graph generation; force-refresh when graph was loaded.
  useEffect(() => {
    const gen = savedJobs.state.externalInvalidation.graphGeneration;
    if (gen <= 0) {
      return;
    }
    if (obs.state.graph.loaded || state.selectedTab === 'graph') {
      void obs.loadGraph({force: true});
    }
    // Generation is the sole invalidation trigger for graph projection.
  }, [savedJobs.state.externalInvalidation.graphGeneration]);

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

  const handleReprocess = (item: CvHistoryItem) => {
    if (!obs.beginReprocess(item.id)) {
      return;
    }
    if (onCvReprocess) {
      const accepted = onCvReprocess(item.id);
      if (!accepted) {
        obs.endReprocess(item.id);
      }
    }
  };

  const handleConfirmDelete = async (
    item: CvHistoryItem,
  ): Promise<'success' | 'duplicate' | 'error'> => {
    const outcome = await obs.confirmDelete(item.id);
    if (outcome === 'success') {
      onCvDeleted?.();
    }
    return outcome;
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
      style={{gridTemplateColumns: '13fr 47fr'}}
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
          <CvManagerPanel
            resource={state.cvHistory}
            selectedAttachmentId={state.selectedAttachmentId}
            pendingByAttachment={state.cvManager.pendingByAttachment}
            errorsByAttachment={state.cvManager.errorsByAttachment}
            onSelect={handleSelectAttachment}
            onOpenFile={handleOpenFile}
            onRefresh={() => {
              void obs.loadCvHistory({force: true});
            }}
            onReprocess={handleReprocess}
            onConfirmDelete={handleConfirmDelete}
            onClearError={obs.clearActionError}
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

        {state.selectedTab === 'saved-jobs' ? (
          <SavedJobsPanel
            list={savedJobs.state.list}
            details={savedJobs.state.details}
            selectedJobId={savedJobs.state.selectedJobId}
            actions={savedJobs.state.actions}
            onSelect={savedJobs.selectJob}
            onLoad={loadSavedJobsList}
            onRefresh={refreshSavedJobsList}
            onEvaluate={savedJobs.evaluateJob}
            onConfirmDelete={savedJobs.confirmDelete}
            onConfirmReextract={savedJobs.confirmReextract}
            onClearError={savedJobs.clearActionError}
            onRefreshDetail={(jobId) => {
              void savedJobs.loadDetail(jobId, {force: true});
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

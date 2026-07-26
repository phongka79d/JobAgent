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
import type {SavedJobsController} from '../jobs/savedJobsState';
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
  savedJobs: SavedJobsController;
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
  /** Shared workspace/chat mutation lock. */
  isInteractionLocked?: boolean;
  /** Pending profiles must never render stale profile-owned inspector data. */
  profileSetupInProgress?: boolean;
  profileId?: string | null;
  profileDisplayName?: string;
  onProfileDelete?: (profileId: string) => Promise<boolean>;
  onCreateTailoredCv?: (jobId: string) => void;
  isTailoringPending?: boolean;
};

export function ObservabilitySidebar({
  overview,
  collapsedStatus,
  observability: obs,
  savedJobs,
  savedJobsInvalidateKey = 0,
  onCvReprocess,
  onCvDeleted,
  isInteractionLocked = false,
  profileSetupInProgress = false,
  profileId = null,
  profileDisplayName = '',
  onProfileDelete,
  onCreateTailoredCv,
  isTailoringPending = false,
}: ObservabilitySidebarProps) {
  const {isCollapsed, toggle} = useSideNavCollapse();
  const {state} = obs;
  const handledSavedJobsInvalidateKey = useRef(savedJobsInvalidateKey);

  const loadSavedJobsList = useCallback(() => {
    void savedJobs.loadList();
  }, [savedJobs.loadList]);

  const refreshSavedJobsList = useCallback(() => {
    void savedJobs.loadList({}, {force: true});
  }, [savedJobs.loadList]);

  useEffect(() => {
    if (profileSetupInProgress) return;
    const controller = new AbortController();
    const {signal} = controller;
    if (state.selectedTab === 'cv-history') {
      void obs.loadCvHistory({signal});
    } else if (state.selectedTab === 'runs') {
      void obs.loadRuns({signal});
    } else if (state.selectedTab === 'graph') {
      void obs.loadGraph({signal});
      void savedJobs.loadList({}, {signal});
    } else if (state.selectedTab === 'saved-jobs') {
      void savedJobs.loadList({}, {signal});
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
    profileSetupInProgress,
    profileId,
    state.selectedTab,
    state.selectedAttachmentId,
    state.activationGeneration,
  ]);

  const selectedSkillMapLoaded = savedJobs.state.selectedJobId
    ? savedJobs.state.skillMaps[savedJobs.state.selectedJobId]?.loaded
    : undefined;

  useEffect(() => {
    if (profileSetupInProgress) return;
    const jobId = savedJobs.state.selectedJobId;
    if (
      state.selectedTab !== 'graph' ||
      !jobId ||
      selectedSkillMapLoaded === true
    ) {
      return;
    }
    const controller = new AbortController();
    void savedJobs.loadSkillMap(jobId, {signal: controller.signal});
    return () => {
      controller.abort();
    };
    // The selected Job and cache freshness own this read. loadSkillMap itself
    // changes as cache state changes, so it is intentionally not a dependency.
  }, [
    profileSetupInProgress,
    profileId,
    state.selectedTab,
    savedJobs.state.selectedJobId,
    selectedSkillMapLoaded,
  ]);

  useEffect(() => {
    if (profileSetupInProgress) return;
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
  }, [
    profileId,
    profileSetupInProgress,
    state.selectedTab,
    savedJobs.state.selectedJobId,
  ]);

  // Saved-JD invalidation signal: mark list/selected detail non-current; force
  // open-tab GETs; closed tab refreshes lazily on next selection/mount.
  useEffect(() => {
    if (profileSetupInProgress) return;
    if (handledSavedJobsInvalidateKey.current === savedJobsInvalidateKey) {
      return;
    }
    handledSavedJobsInvalidateKey.current = savedJobsInvalidateKey;
    const selectedJobId = savedJobs.state.selectedJobId;
    const savedJobsOpen = state.selectedTab === 'saved-jobs';
    const graphOpen = state.selectedTab === 'graph';
    savedJobs.invalidateCurrentness();
    if (savedJobsOpen || graphOpen) {
      void savedJobs.loadList({}, {force: true});
      if (savedJobsOpen && selectedJobId) {
        void savedJobs.loadDetail(selectedJobId, {force: true});
      }
      if (graphOpen && selectedJobId) {
        void savedJobs.loadSkillMap(selectedJobId, {force: true});
      }
    }
    // Signal-only trigger; selection/tab captured at invalidation time (Plan 11).
  }, [profileSetupInProgress, savedJobsInvalidateKey]);

  // Evaluate/delete success bumps graph generation; force-refresh when graph was loaded.
  useEffect(() => {
    if (profileSetupInProgress) return;
    const gen = savedJobs.state.externalInvalidation.graphGeneration;
    if (gen <= 0) {
      return;
    }
    if (obs.state.graph.loaded || state.selectedTab === 'graph') {
      void obs.loadGraph({force: true});
    }
    // Generation is the sole invalidation trigger for graph projection.
  }, [profileSetupInProgress, savedJobs.state.externalInvalidation.graphGeneration]);

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
    if (isInteractionLocked) {
      return;
    }
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
    if (isInteractionLocked) {
      return 'duplicate';
    }
    const outcome = await obs.confirmDelete(item.id, async () => {
      if (!profileId || !onProfileDelete) {
        return false;
      }
      return onProfileDelete(profileId);
    });
    if (outcome === 'success') {
      onCvDeleted?.();
    }
    return outcome;
  };

  const chunkList = state.selectedAttachmentId
    ? state.chunkLists[state.selectedAttachmentId] ?? null
    : null;
  const selectedSkillMap = savedJobs.state.selectedJobId
    ? savedJobs.state.skillMaps[savedJobs.state.selectedJobId] ?? null
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
      data-active-tab={state.selectedTab}
      data-testid="jobagent-obs-root"
      style={{
        gridTemplateColumns:
          state.selectedTab === 'saved-jobs' ? '1fr 5fr' : '13fr 47fr',
      }}
    >
      <div data-testid="jobagent-obs-tabs">
        <ObservabilityTabList
          value={state.selectedTab}
          isCollapsed={false}
          onChange={handleSelectTab}
        />
      </div>

      <div className="jobagent-obs-content">
        {profileSetupInProgress && state.selectedTab !== 'overview' ? (
          <Text data-testid="profile-setup-in-progress" type="supporting">
            Profile setup in progress
          </Text>
        ) : null}

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

        {!profileSetupInProgress && state.selectedTab === 'cv-history' ? (
          <CvManagerPanel
            profileDisplayName={profileDisplayName}
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

        {!profileSetupInProgress && state.selectedTab === 'chunks' ? (
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

        {!profileSetupInProgress && state.selectedTab === 'graph' ? (
          <GraphPanel
            resource={state.graph}
            selectedJobId={savedJobs.state.selectedJobId}
            skillMapResource={selectedSkillMap}
            onRefresh={() => {
              void obs.loadGraph({force: true});
            }}
            onRefreshSkillMap={() => {
              if (!savedJobs.state.selectedJobId) {
                return;
              }
              void savedJobs.loadSkillMap(savedJobs.state.selectedJobId, {
                force: true,
              });
            }}
          />
        ) : null}

        {!profileSetupInProgress && state.selectedTab === 'runs' ? (
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

        {!profileSetupInProgress && state.selectedTab === 'saved-jobs' ? (
          <SavedJobsPanel
            list={savedJobs.state.list}
            details={savedJobs.state.details}
            selectedJobId={savedJobs.state.selectedJobId}
            actions={savedJobs.state.actions}
            onSelect={savedJobs.selectJob}
            onLoad={loadSavedJobsList}
            onRefresh={refreshSavedJobsList}
            onEvaluate={(jobId) =>
              isInteractionLocked ? Promise.resolve('duplicate') : savedJobs.evaluateJob(jobId)
            }
            onConfirmDelete={(jobId) =>
              isInteractionLocked ? Promise.resolve('duplicate') : savedJobs.confirmDelete(jobId)
            }
            onConfirmReextract={(jobId) =>
              isInteractionLocked ? Promise.resolve('duplicate') : savedJobs.confirmReextract(jobId)
            }
            onClearError={savedJobs.clearActionError}
            onRefreshDetail={(jobId) => {
              void savedJobs.loadDetail(jobId, {force: true});
            }}
            canCreateTailoredCv={!profileSetupInProgress && !isInteractionLocked}
            isTailoringPending={isTailoringPending}
            onCreateTailoredCv={onCreateTailoredCv}
          />
        ) : null}
      </div>
    </div>
  );
}

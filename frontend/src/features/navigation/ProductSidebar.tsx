import {useCallback, useEffect, useRef, useState, type ReactNode} from 'react';
import {SideNavItem, SideNavSection, useSideNavCollapse} from '@astryxdesign/core/SideNav';

import {TailoringSessionsPanel} from '../cv-tailoring/TailoringSessionsPanel';
import type {CvTailoringController} from '../cv-tailoring/state';
import {SavedJobsPanel} from '../jobs/SavedJobsPanel';
import type {SavedJobsController} from '../jobs/savedJobsState';
import {PRODUCT_DESTINATIONS, type ProductDestination} from './productNavigation';

export type ProductSidebarProps = {
  readonly overview: ReactNode;
  readonly savedJobs: SavedJobsController;
  readonly tailoring: CvTailoringController;
  readonly savedJobsInvalidateKey: number;
  readonly onCreateTailoredCv?: (jobId: string) => void;
  readonly isTailoringPending?: boolean;
  readonly onOpenTailoringSession?: (sessionId: string) => void;
};

export function ProductSidebar({
  overview,
  savedJobs,
  tailoring,
  savedJobsInvalidateKey,
  onCreateTailoredCv,
  isTailoringPending = false,
  onOpenTailoringSession = () => undefined,
}: ProductSidebarProps) {
  const [selected, setSelected] = useState<ProductDestination>('overview');
  const {isCollapsed, setIsCollapsed} = useSideNavCollapse();
  const handledSavedJobsInvalidateKey = useRef(savedJobsInvalidateKey);

  const refreshPendingSavedJobsInvalidation = useCallback(() => {
    if (handledSavedJobsInvalidateKey.current === savedJobsInvalidateKey) {
      return false;
    }
    handledSavedJobsInvalidateKey.current = savedJobsInvalidateKey;
    void savedJobs.loadList({}, {force: true});
    if (savedJobs.state.selectedJobId !== null) {
      void savedJobs.loadDetail(savedJobs.state.selectedJobId, {force: true});
    }
    return true;
  }, [
    savedJobs.loadDetail,
    savedJobs.loadList,
    savedJobs.state.selectedJobId,
    savedJobsInvalidateKey,
  ]);

  useEffect(() => {
    if (selected !== 'saved-jobs') {
      return;
    }
    refreshPendingSavedJobsInvalidation();
  }, [
    refreshPendingSavedJobsInvalidation,
    selected,
  ]);

  const selectSavedJob = useCallback(
    (jobId: string) => {
      savedJobs.selectJob(jobId);
      void savedJobs.loadDetail(jobId);
    },
    [savedJobs.loadDetail, savedJobs.selectJob],
  );
  const loadSavedJobs = useCallback(() => {
    if (refreshPendingSavedJobsInvalidation()) {
      return;
    }
    void savedJobs.loadList();
  }, [refreshPendingSavedJobsInvalidation, savedJobs.loadList]);
  const refreshSavedJobs = useCallback(() => {
    void savedJobs.loadList({}, {force: true});
  }, [savedJobs.loadList]);
  const refreshSavedJobDetail = useCallback(
    (jobId: string) => {
      void savedJobs.loadDetail(jobId, {force: true});
    },
    [savedJobs.loadDetail],
  );

  const selectDestination = (destination: ProductDestination) => {
    setSelected(destination);
    if (isCollapsed) setIsCollapsed(false);
  };

  return (
    <>
      <SideNavSection title="Workspace">
        {PRODUCT_DESTINATIONS.map((destination) => (
          <SideNavItem
            key={destination.id}
            label={destination.label}
            icon={destination.icon}
            isSelected={selected === destination.id}
            onClick={() => selectDestination(destination.id)}
          />
        ))}
      </SideNavSection>
      {selected === 'overview' ? overview : null}
      {selected === 'saved-jobs' ? (
        <SavedJobsPanel
          list={savedJobs.state.list}
          details={savedJobs.state.details}
          selectedJobId={savedJobs.state.selectedJobId}
          actions={savedJobs.state.actions}
          onSelect={selectSavedJob}
          onLoad={loadSavedJobs}
          onRefresh={refreshSavedJobs}
          onEvaluate={savedJobs.evaluateJob}
          onConfirmDelete={savedJobs.confirmDelete}
          onConfirmReextract={savedJobs.confirmReextract}
          onClearError={savedJobs.clearActionError}
          onRefreshDetail={refreshSavedJobDetail}
          canCreateTailoredCv={Boolean(onCreateTailoredCv)}
          isTailoringPending={isTailoringPending}
          onCreateTailoredCv={onCreateTailoredCv}
        />
      ) : null}
      {selected === 'tailored-cvs' ? (
        <TailoringSessionsPanel
          controller={tailoring}
          onOpenSession={onOpenTailoringSession}
        />
      ) : null}
    </>
  );
}

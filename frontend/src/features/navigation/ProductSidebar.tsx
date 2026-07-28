import {useState, type ReactNode} from 'react';
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
  readonly onCreateTailoredCv?: (jobId: string) => void;
  readonly isTailoringPending?: boolean;
  readonly onOpenTailoringSession?: (sessionId: string) => void;
};

export function ProductSidebar({
  overview,
  savedJobs,
  tailoring,
  onCreateTailoredCv,
  isTailoringPending = false,
  onOpenTailoringSession = () => undefined,
}: ProductSidebarProps) {
  const [selected, setSelected] = useState<ProductDestination>('overview');
  const {isCollapsed, setIsCollapsed} = useSideNavCollapse();

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
          onSelect={savedJobs.selectJob}
          onLoad={() => void savedJobs.loadList()}
          onRefresh={() => void savedJobs.loadList({}, {force: true})}
          onEvaluate={savedJobs.evaluateJob}
          onConfirmDelete={savedJobs.confirmDelete}
          onConfirmReextract={savedJobs.confirmReextract}
          onClearError={savedJobs.clearActionError}
          onRefreshDetail={(jobId) => void savedJobs.loadDetail(jobId, {force: true})}
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

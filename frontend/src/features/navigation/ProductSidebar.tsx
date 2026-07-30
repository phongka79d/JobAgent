import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
} from 'react';
import {SideNavItem, SideNavSection, useSideNavCollapse} from '@astryxdesign/core/SideNav';
import {VStack} from '@astryxdesign/core/VStack';

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
  readonly editorMode?: boolean;
  readonly selectedDestination?: ProductDestination;
  readonly onSelectedDestinationChange?: (destination: ProductDestination) => void;
  readonly editorMemoryRef?: MutableRefObject<ProductSidebarEditorMemory>;
};

export type ProductSidebarEditorMemory = {
  selected: ProductDestination;
  collapsed: boolean;
} | null;

export type ProductSidebarNavProps = {
  readonly selectedDestination: ProductDestination;
  readonly onSelectedDestinationChange: (destination: ProductDestination) => void;
  readonly editorMode?: boolean;
  readonly editorMemoryRef?: MutableRefObject<ProductSidebarEditorMemory>;
};

export function ProductSidebarNav({
  selectedDestination,
  onSelectedDestinationChange,
  editorMode = false,
  editorMemoryRef,
}: ProductSidebarNavProps) {
  const {isCollapsed, toggle: toggleCollapsed} = useSideNavCollapse();
  const localEditorMemoryRef = useRef<ProductSidebarEditorMemory>(null);
  const beforeEditorRef = editorMemoryRef ?? localEditorMemoryRef;

  useEffect(() => {
    if (editorMode) {
      if (beforeEditorRef.current === null) {
        beforeEditorRef.current = {
          selected: selectedDestination,
          collapsed: isCollapsed,
        };
      }
      if (!isCollapsed) toggleCollapsed();
      return;
    }
    const previous = beforeEditorRef.current;
    if (previous !== null) {
      beforeEditorRef.current = null;
      onSelectedDestinationChange(previous.selected);
      if (isCollapsed !== previous.collapsed) toggleCollapsed();
    }
  }, [
    beforeEditorRef,
    editorMode,
    isCollapsed,
    onSelectedDestinationChange,
    selectedDestination,
    toggleCollapsed,
  ]);

  const selectDestination = (destination: ProductDestination) => {
    if (editorMode) return;
    onSelectedDestinationChange(destination);
    if (isCollapsed) toggleCollapsed();
  };

  return (
    <VStack
      gap={2}
      data-testid="jobagent-product-sidebar-nav"
      data-editor-mode={String(editorMode)}
      data-selected-destination={selectedDestination}
    >
      <SideNavSection title="Workspace">
        {PRODUCT_DESTINATIONS.map((destination) => (
          <SideNavItem
            key={destination.id}
            label={destination.label}
            icon={destination.icon}
            isSelected={selectedDestination === destination.id}
            onClick={() => selectDestination(destination.id)}
          />
        ))}
      </SideNavSection>
    </VStack>
  );
}

export type ProductSidebarContentProps = Omit<
  ProductSidebarProps,
  'selectedDestination' | 'onSelectedDestinationChange' | 'editorMemoryRef'
> & {
  readonly selectedDestination: ProductDestination;
};

export function ProductSidebarContent({
  overview,
  savedJobs,
  tailoring,
  savedJobsInvalidateKey,
  onCreateTailoredCv,
  isTailoringPending = false,
  onOpenTailoringSession = () => undefined,
  editorMode = false,
  selectedDestination,
}: ProductSidebarContentProps) {
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
    if (selectedDestination !== 'saved-jobs') {
      return;
    }
    refreshPendingSavedJobsInvalidation();
  }, [refreshPendingSavedJobsInvalidation, selectedDestination]);

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

  return (
    <VStack
      className="jobagent-product-workspace jobagent-hidden-scrollbar"
      gap={2}
      height="100%"
      width="100%"
      data-testid="jobagent-product-workspace"
      data-editor-mode={String(editorMode)}
      data-selected-destination={selectedDestination}
    >
      {!editorMode && selectedDestination === 'overview' ? overview : null}
      {!editorMode && selectedDestination === 'saved-jobs' ? (
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
      {!editorMode && selectedDestination === 'tailored-cvs' ? (
        <TailoringSessionsPanel
          controller={tailoring}
          onOpenSession={onOpenTailoringSession}
        />
      ) : null}
    </VStack>
  );
}

export function ProductSidebar({
  selectedDestination,
  onSelectedDestinationChange,
  editorMemoryRef,
  ...contentProps
}: ProductSidebarProps) {
  const [localSelected, setLocalSelected] =
    useState<ProductDestination>('overview');
  const selected = selectedDestination ?? localSelected;
  const updateSelected = useCallback(
    (destination: ProductDestination) => {
      if (onSelectedDestinationChange) {
        onSelectedDestinationChange(destination);
      } else {
        setLocalSelected(destination);
      }
    },
    [onSelectedDestinationChange],
  );

  return (
    <VStack
      gap={2}
      data-testid="jobagent-product-sidebar"
      data-editor-mode={String(contentProps.editorMode ?? false)}
      data-selected-destination={selected}
    >
      <ProductSidebarNav
        selectedDestination={selected}
        onSelectedDestinationChange={updateSelected}
        editorMode={contentProps.editorMode}
        editorMemoryRef={editorMemoryRef}
      />
      <ProductSidebarContent
        {...contentProps}
        selectedDestination={selected}
      />
    </VStack>
  );
}

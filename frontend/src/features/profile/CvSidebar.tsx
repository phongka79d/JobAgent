/**
 * Approved-profile sidebar with the observability inspector.
 * Profile and upload state stay here; presentation and inspector state are delegated.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {Icon} from '@astryxdesign/core/Icon';
import {NavIcon} from '@astryxdesign/core/NavIcon';
import {
  SideNav,
  SideNavCollapseButton,
  SideNavHeading,
  useSideNavCollapse,
  useSideNavRenderMode,
} from '@astryxdesign/core/SideNav';

import type {ObservabilityApi} from '../observability/api';
import {ObservabilitySidebar} from '../observability/ObservabilitySidebar';
import {useObservabilityState} from '../observability/state';
import {
  ChatApiError,
  fetchProfile,
  getActiveCvUrl,
  uploadCv,
} from './api';
import {ProfileOverviewPanel} from './ProfileOverviewPanel';
import type {CvUploadResponse, ProfileReadResponse} from './types';

export type CvSidebarDeps = {
  loadProfile?: typeof fetchProfile;
  uploadCv?: typeof uploadCv;
  getActiveCvUrl?: typeof getActiveCvUrl;
  observability?: Partial<ObservabilityApi>;
};

export type CvSidebarProps = {
  /** True while a run is connecting/streaming/interrupted - disables upload. */
  isUploadDisabled: boolean;
  /** Called after a successful upload so the chat can start an ID-only turn. */
  onSidebarUploadSuccess: (result: CvUploadResponse) => void;
  /** Increment / change to force a profile reload (e.g. after Save Profile). */
  refreshKey?: number;
  deps?: CvSidebarDeps;
};

function profileStateLabel(profile: ProfileReadResponse | null): {
  text: string;
  variant: 'success' | 'neutral' | 'warning' | 'error';
} {
  if (profile === null) {
    return {text: 'Loading...', variant: 'neutral'};
  }
  if (profile.present) {
    const title = profile.profile?.current_title?.trim();
    return {
      text: title ? `Active - ${title}` : 'Active profile',
      variant: 'success',
    };
  }
  if (profile.draft_present) {
    return {
      text: 'Draft ready - click Save Profile in chat',
      variant: 'warning',
    };
  }
  return {text: 'No approved profile', variant: 'neutral'};
}

function SidebarCollapseControl() {
  const {isCollapsed} = useSideNavCollapse();
  return (
    <SideNavCollapseButton
      aria-expanded={!isCollapsed}
      data-testid="jobagent-sidebar-collapse"
    />
  );
}

function CvSidebarShell({children}: {children?: ReactNode}) {
  const viewportWidth = window.innerWidth;

  return (
    <SideNav
      resizable={{
        defaultWidth: Math.round(viewportWidth * 0.6),
        minWidth: 360,
        maxWidth: Math.round(viewportWidth * 0.72),
        autoSaveId: 'jobagent-observability-sidebar-width-v2',
      }}
      collapsible={{hasButton: false}}
      className="jobagent-cv-sidebar-shell"
      header={
        <SideNavHeading
          heading="JobAgent"
          subheading="CV & profile"
          icon={<NavIcon icon={<Icon icon="search" />} />}
        />
      }
      footerIcons={<SidebarCollapseControl />}
      data-testid="jobagent-cv-sidebar"
    >
      {children}
    </SideNav>
  );
}

export function CvSidebar(props: CvSidebarProps) {
  const renderMode = useSideNavRenderMode();

  if (renderMode === 'topbar') {
    return <CvSidebarShell />;
  }

  return <CvSidebarController {...props} />;
}

function CvSidebarController({
  isUploadDisabled,
  onSidebarUploadSuccess,
  refreshKey = 0,
  deps,
}: CvSidebarProps) {
  const observability = useObservabilityState({api: deps?.observability});
  const loadProfile = deps?.loadProfile ?? fetchProfile;
  const doUpload = deps?.uploadCv ?? uploadCv;
  const cvUrl = deps?.getActiveCvUrl ?? getActiveCvUrl;

  const [profile, setProfile] = useState<ProfileReadResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const loadedRefreshKey = useRef(refreshKey);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadProfile(signal);
        if (!signal?.aborted) {
          setProfile(next);
          setLoadError(null);
        }
      } catch (err) {
        if (signal?.aborted) {
          return;
        }
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'Failed to load profile';
        setLoadError(summary);
      }
    },
    [loadProfile],
  );

  useEffect(() => {
    const isRefreshRequested = loadedRefreshKey.current !== refreshKey;
    loadedRefreshKey.current = refreshKey;
    if (profile !== null && !isRefreshRequested) {
      return;
    }

    const controller = new AbortController();
    void reload(controller.signal);
    return () => {
      controller.abort();
    };
  }, [profile, reload, refreshKey]);

  const handleFileChange = useCallback(
    (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      setSelectedFile(file);
      setUploadError(null);
    },
    [],
  );

  const handleUpload = useCallback(
    async (files: File | File[] | null) => {
      const file = Array.isArray(files) ? (files[0] ?? null) : files;
      if (!file || isUploadDisabled || isUploading) {
        return;
      }
      setIsUploading(true);
      setUploadError(null);
      try {
        const result = await doUpload(file);
        setSelectedFile(null);
        await reload();
        onSidebarUploadSuccess(result);
      } catch (err) {
        const code = err instanceof ChatApiError ? err.code : 'UPLOAD_FAILED';
        const summary =
          err instanceof ChatApiError
            ? err.summary
            : err instanceof Error
              ? err.message
              : 'CV upload failed';
        setUploadError(`${summary} (${code})`);
      } finally {
        setIsUploading(false);
      }
    },
    [doUpload, isUploadDisabled, isUploading, onSidebarUploadSuccess, reload],
  );

  const handleViewDownload = useCallback(() => {
    if (!profile?.present || !profile.active_attachment) {
      return;
    }
    window.open(cvUrl(), '_blank', 'noopener,noreferrer');
  }, [cvUrl, profile]);

  const state = profileStateLabel(profile);
  const activeName = profile?.active_attachment?.original_name ?? null;
  const pendingName = profile?.pending_attachment?.original_name ?? null;
  const displayCvName = activeName ?? pendingName;
  const hasActive = Boolean(profile?.present && activeName);
  const uploadLabel = hasActive ? 'Replace CV' : 'Upload CV';
  const disabledReason = isUploadDisabled
    ? 'Upload is disabled while a run is active or waiting for approval'
    : undefined;
  const cvName = displayCvName
    ? hasActive
      ? displayCvName
      : `${displayCvName} (staged - not saved)`
    : 'No active CV';

  const overview = (
    <ProfileOverviewPanel
      stateLabel={state.text}
      stateVariant={state.variant}
      cvName={cvName}
      selectedFile={selectedFile}
      loadError={loadError}
      uploadError={uploadError}
      uploadLabel={uploadLabel}
      isUploadDisabled={isUploadDisabled}
      isUploading={isUploading}
      disabledReason={disabledReason}
      canViewDownload={hasActive}
      onFileChange={handleFileChange}
      onUpload={handleUpload}
      onViewDownload={handleViewDownload}
    />
  );

  return (
    <CvSidebarShell>
      <ObservabilitySidebar
        overview={overview}
        collapsedStatus={{
          label: state.text,
          variant: state.variant,
          cvName: displayCvName,
        }}
        observability={observability}
      />
    </CvSidebarShell>
  );
}

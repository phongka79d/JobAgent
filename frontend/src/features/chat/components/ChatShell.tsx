/**
 * Base Astryx chat shell: AppShell + profile sideNav + ChatLayout.
 * Consumes shared profile upload client/state and chat controller only —
 * no direct store/provider access.
 */

import { useCallback } from "react";

import { Theme } from "@astryxdesign/core";
import { AppShell } from "@astryxdesign/core/AppShell";
import { Banner } from "@astryxdesign/core/Banner";
import { ChatLayout } from "@astryxdesign/core/Chat";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { VStack } from "@astryxdesign/core/VStack";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

import { SIDEBAR_PROFILE_TURN_TEXT } from "../../profile/contracts";
import { ProfileSidebar } from "../../profile/components/ProfileSidebar";
import {
  useProfileShellState,
  type ProfileShellApi,
} from "../../profile/components/useProfileShellState";
import type { HistoryMessage } from "../contracts";
import type { ChatState } from "../reducer";
import {
  runComposerCvUpload,
  runSidebarCvUpload,
} from "./chatUploadHandlers";
import { ChatComposerPanel } from "./ChatComposerPanel";
import { ChatMessages } from "./ChatMessages";
import {
  useChatController,
  type ChatShellApi,
} from "./useChatController";

export type { ChatShellApi };

export interface ChatShellProps {
  /** Skip automatic history hydration (tests with deterministic state). */
  readonly skipHydrate?: boolean;
  /** Seed messages before/without network hydration. */
  readonly initialMessages?: readonly HistoryMessage[];
  /** Injectable transport for tests. */
  readonly api?: Partial<ChatShellApi>;
  /** Optional controlled initial reducer state for deterministic UI tests. */
  readonly initialState?: ChatState;
  /** When false, Theme wrapper is omitted (App already provides Theme). */
  readonly wrapTheme?: boolean;
  /** When false, profile sidebar and its fetches are skipped (unit tests). */
  readonly enableProfileSidebar?: boolean;
  /** Injectable profile clients for tests. */
  readonly profileApi?: ProfileShellApi;
}

/**
 * Full-page chat experience: AppShell (sideNav profile) + ChatLayout.
 */
export function ChatShell({
  skipHydrate = false,
  initialMessages,
  api: apiOverrides,
  initialState,
  wrapTheme = true,
  enableProfileSidebar = true,
  profileApi,
}: ChatShellProps) {
  const {
    profile,
    profileLoading,
    profileError,
    uploadState,
    dispatchUpload,
    refreshProfile,
    beginUpload,
    endUpload,
    runUpload,
    activeCvHref,
  } = useProfileShellState(enableProfileSidebar, profileApi);

  const {
    state,
    draft,
    setDraft,
    hydrating,
    hydrateError,
    correctionMode,
    sendDisabled,
    isStopShown,
    composerStatus,
    composerPlaceholder,
    approvalDisabled,
    focusRequestKey,
    handleSubmit,
    handleStop,
    handleResume,
    enterCorrectionMode,
    submitSidebarCvTurn,
  } = useChatController({
    skipHydrate,
    initialMessages,
    api: apiOverrides,
    initialState,
    onRunCompleted: enableProfileSidebar ? refreshProfile : undefined,
  });

  const handleSidebarUploadFile = useCallback(
    (file: File) =>
      runSidebarCvUpload({
        file,
        beginUpload,
        endUpload,
        runUpload,
        dispatchUpload,
        submitSidebarCvTurn,
        sidebarTurnText: SIDEBAR_PROFILE_TURN_TEXT,
      }),
    [beginUpload, dispatchUpload, endUpload, runUpload, submitSidebarCvTurn],
  );

  const handleComposerUploadFile = useCallback(
    (file: File) =>
      runComposerCvUpload({
        file,
        beginUpload,
        endUpload,
        runUpload,
        dispatchUpload,
      }),
    [beginUpload, dispatchUpload, endUpload, runUpload],
  );

  const handleRemoveUpload = useCallback(() => {
    dispatchUpload({ type: "REMOVE" });
  }, [dispatchUpload]);

  const handleComposerSubmit = useCallback(
    (value: string) => {
      const attachmentId =
        !correctionMode && uploadState.phase === "uploaded"
          ? uploadState.attachmentId
          : null;
      const ids = attachmentId ? [attachmentId] : undefined;
      const accepted = handleSubmit(value, ids);
      if (accepted && ids && ids.length > 0) {
        dispatchUpload({ type: "REMOVE" });
      }
    },
    [
      correctionMode,
      dispatchUpload,
      handleSubmit,
      uploadState.attachmentId,
      uploadState.phase,
    ],
  );

  const emptyState = (
    <EmptyState
      title="Start a conversation"
      description="Ask JobAgent about your career workflow. Messages stream here with tool activity when the agent works."
      headingLevel={1}
      data-testid="chat-empty-state"
    />
  );

  const hasMessages =
    state.messages.length > 0 ||
    state.streamingText.length > 0 ||
    state.tools.length > 0 ||
    state.phase === "active" ||
    state.phase === "awaiting_approval" ||
    state.phase === "failed" ||
    state.phase === "disconnected" ||
    state.phase === "completed";

  const body = hydrating ? (
    <VStack gap={4} data-testid="chat-loading">
      <Spinner label="Loading conversation…" size="md" />
    </VStack>
  ) : (
    <ChatLayout
      density="balanced"
      emptyState={!hasMessages ? emptyState : undefined}
      composer={
        <ChatComposerPanel
          value={draft}
          onChange={setDraft}
          onSubmit={handleComposerSubmit}
          onStop={handleStop}
          isDisabled={sendDisabled}
          isStopShown={isStopShown}
          status={composerStatus}
          placeholder={composerPlaceholder}
          uploadState={uploadState}
          onUploadFile={handleComposerUploadFile}
          onRemoveUpload={handleRemoveUpload}
          focusRequestKey={focusRequestKey}
        />
      }
      data-testid="chat-layout"
    >
      {hasMessages ? (
        <ChatMessages
          messages={state.messages}
          phase={state.phase}
          streamingText={state.streamingText}
          tools={state.tools}
          assistantStatus={state.assistantStatus}
          assistantStatusMessage={state.assistantStatusMessage}
          approval={state.approval}
          failure={state.failure}
          streamError={state.streamError}
          approvalDisabled={approvalDisabled}
          onApprove={() => {
            handleResume("approve");
          }}
          onCorrect={(correctionText) => {
            handleResume("correct", correctionText);
          }}
          onRequestChanges={enterCorrectionMode}
        />
      ) : null}
    </ChatLayout>
  );

  const sideNav = enableProfileSidebar ? (
    <ProfileSidebar
      profile={profile}
      profileLoading={profileLoading}
      profileError={profileError}
      uploadState={uploadState}
      onUploadFile={handleSidebarUploadFile}
      onRemoveUpload={handleRemoveUpload}
      activeCvHref={activeCvHref}
      uploadDisabled={false}
    />
  ) : undefined;

  const shell = (
    <AppShell
      contentPadding={0}
      height="fill"
      variant="surface"
      sideNav={sideNav}
      banner={
        hydrateError ? (
          <Banner
            status="error"
            title="History unavailable"
            description="The chat shell is ready. Retry by reloading, or send a new message once the API is reachable."
            container="section"
            data-testid="chat-hydrate-banner"
          />
        ) : undefined
      }
      data-testid="chat-app-shell"
    >
      {body}
    </AppShell>
  );

  if (!wrapTheme) {
    return shell;
  }

  return (
    <Theme theme={neutralTheme} mode="system">
      {shell}
    </Theme>
  );
}

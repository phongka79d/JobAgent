/**
 * Profile load + shared CV upload wiring for ChatShell sideNav.
 * Owns profile fetch lifecycle and upload-in-flight guard only.
 */

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { activeCvUrl, fetchProfile, uploadCv } from "../api";
import type { ProfileResponse } from "../contracts";
import {
  createInitialUploadState,
  uploadReducer,
} from "../state/uploadState";

export interface ProfileShellApi {
  readonly fetchProfile?: typeof fetchProfile;
  readonly uploadCv?: typeof uploadCv;
  readonly activeCvUrl?: typeof activeCvUrl;
}

export function useProfileShellState(
  enabled: boolean,
  profileApi?: ProfileShellApi,
) {
  const loadProfile = profileApi?.fetchProfile ?? fetchProfile;
  const doUpload = profileApi?.uploadCv ?? uploadCv;
  const cvUrlFor = profileApi?.activeCvUrl ?? activeCvUrl;

  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileLoading, setProfileLoading] = useState(enabled);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [uploadState, dispatchUpload] = useReducer(
    uploadReducer,
    undefined,
    createInitialUploadState,
  );
  const uploadInFlightRef = useRef(false);

  const refreshProfile = useCallback(() => {
    if (!enabled) {
      return;
    }
    setProfileLoading(true);
    void loadProfile()
      .then((doc) => {
        setProfile(doc);
        setProfileError(null);
        setProfileLoading(false);
      })
      .catch((error: unknown) => {
        const message =
          error instanceof Error ? error.message : "Failed to load profile";
        setProfileError(message);
        setProfileLoading(false);
      });
  }, [enabled, loadProfile]);

  useEffect(() => {
    if (!enabled) {
      setProfileLoading(false);
      return;
    }
    const controller = new AbortController();
    setProfileLoading(true);
    setProfileError(null);
    void loadProfile({ signal: controller.signal })
      .then((doc) => {
        if (controller.signal.aborted) {
          return;
        }
        setProfile(doc);
        setProfileLoading(false);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "Failed to load profile";
        setProfileError(message);
        setProfileLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [enabled, loadProfile]);

  const beginUpload = useCallback((): boolean => {
    if (uploadInFlightRef.current) {
      return false;
    }
    uploadInFlightRef.current = true;
    return true;
  }, []);

  const endUpload = useCallback(() => {
    uploadInFlightRef.current = false;
  }, []);

  const runUpload = useCallback(
    async (file: File) => {
      return doUpload(file);
    },
    [doUpload],
  );

  const activeCvHref =
    profile?.state === "active" && profile.active_attachment
      ? cvUrlFor()
      : null;

  return {
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
  };
}

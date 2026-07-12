/**
 * @vitest-environment node
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  activeCvUrl,
  fetchProfile,
  profileUrl,
  ProfileApiError,
  uploadCv,
  uploadCvUrl,
} from "./api";
import {
  parseProfileResponse,
  parseStagedAttachmentResponse,
  PROFILE_API_PATHS,
  SIDEBAR_PROFILE_TURN_TEXT,
} from "./contracts";

const BASE = "http://127.0.0.1:8000";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("profile contracts", () => {
  it("parses none and active envelopes and rejects inconsistent none payloads", () => {
    expect(parseProfileResponse({ state: "none", profile: null, preferences: null, active_attachment: null })).toEqual({
      state: "none",
      profile: null,
      preferences: null,
      active_attachment: null,
    });

    const active = parseProfileResponse({
      state: "active",
      profile: { summary: "Engineer" },
      preferences: null,
      active_attachment: {
        id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        original_name: "cv.pdf",
        mime_type: "application/pdf",
        size_bytes: 12,
        page_count: 1,
        state: "active",
      },
    });
    expect(active.state).toBe("active");
    expect(active.active_attachment?.original_name).toBe("cv.pdf");

    expect(() =>
      parseProfileResponse({
        state: "none",
        profile: { summary: "x" },
        preferences: null,
        active_attachment: null,
      }),
    ).toThrow(/no-profile/);
  });

  it("parses staged upload metadata and rejects missing id", () => {
    const staged = parseStagedAttachmentResponse({
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      original_name: "resume.pdf",
      mime_type: "application/pdf",
      size_bytes: 100,
      page_count: 2,
      state: "staged",
    });
    expect(staged.id).toMatch(/^bbbb/);
    expect(() =>
      parseStagedAttachmentResponse({
        original_name: "x.pdf",
        mime_type: "application/pdf",
        size_bytes: 1,
        page_count: 1,
        state: "staged",
      }),
    ).toThrow(/id/);
  });

  it("exposes the source-approved sidebar turn text without PII tokens", () => {
    expect(SIDEBAR_PROFILE_TURN_TEXT).toBe(
      "Create a candidate profile draft from the attached CV.",
    );
    expect(SIDEBAR_PROFILE_TURN_TEXT).not.toMatch(/@|\+1|ssn|password/i);
  });
});

describe("profile URL helpers", () => {
  it("builds only the approved profile and upload paths", () => {
    expect(profileUrl(BASE)).toBe(`${BASE}/api/profile`);
    expect(activeCvUrl(BASE)).toBe(`${BASE}/api/profile/cv`);
    expect(uploadCvUrl(BASE)).toBe(`${BASE}/api/attachments/cv`);
    expect(PROFILE_API_PATHS.profile).toBe("/api/profile");
    expect(PROFILE_API_PATHS.upload).toBe("/api/attachments/cv");
  });
});

describe("fetchProfile", () => {
  it("loads a typed profile document from GET /api/profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        expect(String(input)).toBe(`${BASE}/api/profile`);
        return new Response(
          JSON.stringify({
            state: "none",
            profile: null,
            preferences: null,
            active_attachment: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );

    const doc = await fetchProfile({ baseUrl: BASE });
    expect(doc.state).toBe("none");
  });

  it("maps object detail codes to ProfileApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: { code: "PROFILE_INVALID" } }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(fetchProfile({ baseUrl: BASE })).rejects.toMatchObject({
      name: "ProfileApiError",
      status: 400,
      code: "PROFILE_INVALID",
    } satisfies Partial<ProfileApiError>);
  });
});

describe("uploadCv", () => {
  it("POSTs multipart FormData with field name file and parses the body", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(`${BASE}/api/attachments/cv`);
      expect(init?.method).toBe("POST");
      expect(init?.body).toBeInstanceOf(FormData);
      const form = init?.body as FormData;
      const file = form.get("file");
      expect(file).toBeInstanceOf(File);
      expect((file as File).name).toBe("mine.pdf");
      // Content-Type must not be forced (boundary is runtime-owned).
      const headers = init?.headers as Record<string, string> | undefined;
      expect(headers?.["Content-Type"]).toBeUndefined();
      return new Response(
        JSON.stringify({
          id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
          original_name: "mine.pdf",
          mime_type: "application/pdf",
          size_bytes: 4,
          page_count: 1,
          state: "staged",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });

    const file = new File(["%PDF"], "mine.pdf", { type: "application/pdf" });
    const result = await uploadCv(file, { baseUrl: BASE, fetchImpl });
    expect(result.id).toBe("cccccccc-cccc-cccc-cccc-cccccccccccc");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("surfaces stable upload error codes from detail.code", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { code: "UNSUPPORTED_MEDIA_TYPE" } }),
        { status: 415, headers: { "Content-Type": "application/json" } },
      ),
    );
    const file = new File(["x"], "x.txt", { type: "text/plain" });
    await expect(uploadCv(file, { baseUrl: BASE, fetchImpl })).rejects.toMatchObject({
      name: "ProfileApiError",
      status: 415,
      code: "UNSUPPORTED_MEDIA_TYPE",
    });
  });
});

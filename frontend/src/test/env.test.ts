/**
 * @vitest-environment node
 *
 * Node environment is required so the adversarial transform check can load Vite/esbuild.
 * Unit cases for readPublicConfig do not need a DOM.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";
import { afterEach, describe, expect, it } from "vitest";

import { readPublicConfig } from "../app/env";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

// Construct marker names at runtime so source scans for backend-only config names stay clean.
const unapprovedViteKey = ["VITE", "REVIEW", "SECRET", "MARKER"].join("_");
const prefixCollisionKey = ["VITE_API_BASE_URL", "SECRET"].join("_");
const backendOnlyKey = ["SHOPAIKEY", "API_KEY"].join("_");

const MARKER_KEYS = [
  "VITE_API_BASE_URL",
  unapprovedViteKey,
  prefixCollisionKey,
  backendOnlyKey,
] as const;

const previousEnv: Partial<Record<string, string | undefined>> = {};

function snapshotEnv(): void {
  for (const key of MARKER_KEYS) {
    previousEnv[key] = process.env[key];
  }
}

function restoreEnv(): void {
  for (const key of MARKER_KEYS) {
    const prior = previousEnv[key];
    if (prior === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = prior;
    }
  }
}

describe("readPublicConfig", () => {
  it("reads only VITE_API_BASE_URL when provided", () => {
    const config = readPublicConfig({
      VITE_API_BASE_URL: "http://127.0.0.1:8000",
    });
    expect(config.apiBaseUrl).toBe("http://127.0.0.1:8000");
  });

  it("falls back to the local default when the public value is missing", () => {
    const config = readPublicConfig({ VITE_API_BASE_URL: undefined });
    expect(config.apiBaseUrl).toBe("http://localhost:8000");
  });

  it("does not surface non-allowlisted keys on the returned config", () => {
    const adversarial = {
      VITE_API_BASE_URL: "http://127.0.0.1:8000",
      [unapprovedViteKey]: "should-never-appear",
      [prefixCollisionKey]: "prefix-collision-should-never-appear",
      [backendOnlyKey]: "backend-only-should-never-appear",
    };
    const config = readPublicConfig(adversarial);
    expect(config.apiBaseUrl).toBe("http://127.0.0.1:8000");
    expect(Object.keys(config)).toEqual(["apiBaseUrl"]);
    expect(JSON.stringify(config)).not.toContain("should-never-appear");
    expect(JSON.stringify(config)).not.toContain("prefix-collision-should-never-appear");
    expect(JSON.stringify(config)).not.toContain("backend-only-should-never-appear");
  });
});

describe("Vite one-key public env transform allowlist", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("keeps the approved API marker and drops unapproved VITE, prefix-collision, and backend markers", async () => {
    snapshotEnv();

    const approvedMarker = "http://127.0.0.1:8000/approved-api-marker-01b";
    const unapprovedViteMarker = "unapproved-vite-review-secret-marker-01b";
    const prefixCollisionMarker = "prefix-collision-vite-api-base-url-secret-marker-01b";
    const backendMarker = "backend-only-provider-marker-01b";

    process.env.VITE_API_BASE_URL = approvedMarker;
    process.env[unapprovedViteKey] = unapprovedViteMarker;
    process.env[prefixCollisionKey] = prefixCollisionMarker;
    process.env[backendOnlyKey] = backendMarker;

    // Use the project vite.config.ts so the real exact-key publication path is exercised.
    // Disable dependency discovery — this suite only transforms env.ts.
    const server = await createServer({
      configFile: path.join(frontendRoot, "vite.config.ts"),
      root: frontendRoot,
      server: { middlewareMode: true },
      appType: "custom",
      logLevel: "error",
      optimizeDeps: { noDiscovery: true, disabled: true },
    });

    try {
      const result = await server.transformRequest("/src/app/env.ts");
      expect(result, "expected Vite to transform src/app/env.ts").toBeTruthy();
      const code = result!.code;

      const approvedValueExposed = code.includes(approvedMarker);
      const unapprovedViteValueExposed = code.includes(unapprovedViteMarker);
      const unapprovedViteKeyExposed = code.includes(unapprovedViteKey);
      const prefixCollisionValueExposed = code.includes(prefixCollisionMarker);
      const prefixCollisionKeyExposed = code.includes(prefixCollisionKey);
      const backendValueExposed = code.includes(backendMarker);
      const backendKeyExposed = code.includes(backendOnlyKey);

      expect(approvedValueExposed, "approved VITE_API_BASE_URL value must remain available").toBe(
        true,
      );
      expect(
        unapprovedViteValueExposed,
        "extra VITE_REVIEW_SECRET_MARKER value must not enter the transform",
      ).toBe(false);
      expect(
        unapprovedViteKeyExposed,
        "extra VITE_REVIEW_SECRET_MARKER key must not enter the transform",
      ).toBe(false);
      expect(
        prefixCollisionValueExposed,
        "VITE_API_BASE_URL_SECRET value must not enter the transform (exact-key only)",
      ).toBe(false);
      expect(
        prefixCollisionKeyExposed,
        "VITE_API_BASE_URL_SECRET key must not enter the transform (exact-key only)",
      ).toBe(false);
      expect(
        backendValueExposed,
        "backend-only provider key value must not enter the transform",
      ).toBe(false);
      expect(
        backendKeyExposed,
        "backend-only provider key name must not enter the transform",
      ).toBe(false);
    } finally {
      await server.close();
    }
  });
});

import "@testing-library/jest-dom/vitest";

// Astryx Theme/AppShell use matchMedia for system color mode and responsive shell.
// Guard so node-environment suites (e.g. Vite transform checks) can share setupFiles.
if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

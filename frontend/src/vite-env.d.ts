/// <reference types="vite/client" />

declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string;
  export function readdirSync(path: string): string[];
  export function statSync(path: string): {isDirectory(): boolean};
}

declare module 'node:path' {
  export function join(...paths: string[]): string;
  export function normalize(path: string): string;
}

declare const process: {
  cwd(): string;
};

/**
 * Frontend runtime may read only VITE_API_BASE_URL.
 * No nested frontend .env; Compose/root env injects this name for the client.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/// <reference types="vite/client" />

interface ImportMeta {
  readonly glob: <T = unknown>(
    globs: string | string[],
    opts?: { query?: string; import?: string; eager?: boolean },
  ) => Record<string, T>;
}

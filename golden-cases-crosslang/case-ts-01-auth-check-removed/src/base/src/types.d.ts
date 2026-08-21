// Offline type shims for node:test / node:assert (the sample bundles no
// dependencies, so @types/node is not available; these declarations let
// "tsc --noEmit" pass fully offline. Runtime execution does not need them:
// node --test strips the erasable TS syntax itself (Node >= 23.6).
declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
}
declare module "node:assert/strict" {
  const assert: { equal(actual: unknown, expected: unknown, message?: string): void };
  export default assert;
}

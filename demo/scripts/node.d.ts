/** The one Node API the example generator uses. The demo's tsconfig loads no
 * Node types because everything else here runs in a browser. */
declare module "node:fs" {
  export function writeFileSync(path: string, data: string): void
}

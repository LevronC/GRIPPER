/** Shared route paths for the GRIPPER application. */
export const routes = {
  home: '/',
  terminal: '/app',
  terminalLogin: '/app?mode=login',
  docs: '/docs',
  apiDocs: '/api/docs',
} as const

/** Accounts are invitation-only; the terminal always opens on the sign-in screen. */
export function terminalPath(): string {
  return routes.terminalLogin
}

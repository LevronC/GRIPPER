/** Shared route paths for the GRIPPER application. */
export const routes = {
  home: '/',
  terminal: '/app',
  terminalLogin: '/app?mode=login',
  terminalRegister: '/app?mode=register',
  docs: '/docs',
  apiDocs: '/api/docs',
} as const

export type AuthMode = 'login' | 'register' | 'verify' | 'forgot' | 'reset'

export function terminalPath(mode?: AuthMode): string {
  if (!mode || mode === 'login') return routes.terminalLogin
  return `${routes.terminal}?mode=${mode}`
}

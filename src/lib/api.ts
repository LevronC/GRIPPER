export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export function apiUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

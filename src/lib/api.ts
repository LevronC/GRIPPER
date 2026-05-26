export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export function apiUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

export async function parseApiError(
  res: Response,
  fallback: string,
): Promise<string> {
  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      const data = (await res.json()) as { detail?: string | Array<{ msg?: string }> };
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail) && data.detail[0]?.msg) {
        return data.detail.map((item) => item.msg).filter(Boolean).join(', ');
      }
    } catch {
      return fallback;
    }
  }

  const text = (await res.text()).trim();
  if (text && !text.startsWith('<!')) return text;
  return fallback;
}

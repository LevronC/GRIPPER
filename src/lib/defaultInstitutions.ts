import type { Institution } from '../store/useStore'

/** Must stay in sync with backend/app/db/seed.py DEFAULT_INSTITUTIONS */
export const DEFAULT_INSTITUTIONS: Institution[] = [
  {
    id: '4229435f-f427-4b6b-a432-1f6488157381',
    name: 'Stetson University',
    slug: 'stetson',
    tier: 'enterprise',
  },
  {
    id: '7c8d9e0f-1a2b-3c4d-5e6f-708192a3b4c5',
    name: 'University of Florida',
    slug: 'uf',
    tier: 'enterprise',
  },
  {
    id: '9e0f1a2b-3c4d-5e6f-7081-92a3b4c5d6e7',
    name: 'RGIP Demo Program',
    slug: 'rgip-demo',
    tier: 'free',
  },
]

export const DEMO_LOGIN_HINT = {
  email: 'analyst@stetson.edu',
  password: 'Gripp3rDemo!',
  institutionName: 'Stetson University',
} as const

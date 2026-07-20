import { create } from 'zustand';
import { apiUrl } from '../lib/api';
import { DEFAULT_INSTITUTIONS } from '../lib/defaultInstitutions';

export interface Institution {
  id: string;
  name: string;
  slug: string;
  tier: string;
}

export interface Portfolio {
  id: string;
  name: string;
  strategy_type: string;
  institution_id: string;
}

export interface Holding {
  id?: string;
  ticker: string;
  weight: number;
  cost_basis: number;
  conviction_score?: number | null;
}

export interface Violation {
  id: string;
  event_type: string;
  severity: string;
  details: {
    message: string;
    ticker?: string;
    sector?: string;
    current_weight?: number;
    threshold?: number;
    tickers?: string[];
  };
  resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface ResearchReport {
  id: string;
  sector: string;
  company: string;
  recommendation: string;
  status: string;
  created_at: string;
}

interface GripperState {
  // Auth state
  token: string | null;
  currentUser: {
    id: string;
    email: string;
    role: string;
    institution_id: string;
    graduation_year?: number | null;
  } | null;

  institutions: Institution[];
  currentInstitution: Institution | null;
  portfolios: Portfolio[];
  currentPortfolio: Portfolio | null;
  holdings: Holding[];
  violations: Violation[];
  resolvedViolations: Violation[];
  documents: ResearchReport[];
  simulatedViolations: Violation[];
  
  activeTab: string;
  isLoading: boolean;
  
  // Actions
  setActiveTab: (tab: string) => void;
  setInstitution: (inst: Institution) => Promise<void>;
  setPortfolio: (p: Portfolio) => Promise<void>;
  
  // Auth Actions
    login: (email: string, password: string, instId: string) => Promise<{ ok: boolean; error?: string }>;
  register: (email: string, password: string, instId: string, role: string, graduationYear?: number) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;

  fetchInstitutions: () => Promise<void>;
  fetchPortfolios: (instId: string) => Promise<void>;
  fetchHoldings: (portfolioId: string, instId: string) => Promise<void>;
  fetchViolations: (portfolioId: string, instId: string) => Promise<void>;
  fetchResolvedViolations: (portfolioId: string, instId: string) => Promise<void>;
  fetchDocuments: (instId: string) => Promise<void>;
  
  evaluateCompliance: (portfolioId: string, instId: string) => Promise<void>;
  simulateCompliance: (portfolioId: string, instId: string, holdings: Holding[]) => Promise<void>;
  saveHoldings: (portfolioId: string, instId: string, holdings: Holding[]) => Promise<void>;
}

// Retrieve initial values from localStorage safely
const savedToken = localStorage.getItem('gripper_token');
let savedUser = null;
try {
  const userStr = localStorage.getItem('gripper_user');
  if (userStr) savedUser = JSON.parse(userStr);
} catch (e) {
  console.error('Failed to parse saved user', e);
}

export const useStore = create<GripperState>((set, get) => {
  // Helper to construct headers with auth token and institution ID context
  const getHeaders = (instId?: string) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (get().token) {
      headers['Authorization'] = `Bearer ${get().token}`;
    }
    if (instId) {
      headers['X-Institution-ID'] = instId;
    }
    return headers;
  };

  return {
    token: savedToken,
    currentUser: savedUser,
    institutions: [],
    currentInstitution: null,
    portfolios: [],
    currentPortfolio: null,
    holdings: [],
    violations: [],
    resolvedViolations: [],
    documents: [],
    simulatedViolations: [],
    activeTab: 'Dashboard',
    isLoading: false,

    setActiveTab: (tab) => set({ activeTab: tab }),

    setInstitution: async (inst) => {
      set({ currentInstitution: inst, portfolios: [], currentPortfolio: null, holdings: [], violations: [], resolvedViolations: [], documents: [] });
      await get().fetchPortfolios(inst.id);
      await get().fetchDocuments(inst.id);
    },

    setPortfolio: async (portfolio) => {
      set({ currentPortfolio: portfolio, holdings: [], violations: [], resolvedViolations: [], simulatedViolations: [] });
      const inst = get().currentInstitution;
      if (inst) {
        await get().fetchHoldings(portfolio.id, inst.id);
        await get().fetchViolations(portfolio.id, inst.id);
        await get().fetchResolvedViolations(portfolio.id, inst.id);
      }
    },

    // Auth Actions
    login: async (email, password, instId) => {
      set({ isLoading: true });
      try {
        const res = await fetch(apiUrl('/auth/login'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Institution-ID': instId
          },
          body: JSON.stringify({ email, password })
        });
        if (res.ok) {
          const data = await res.json();
          if (instId && data.institution_id !== instId) {
            return {
              ok: false,
              error: 'Selected institution does not match your account. Choose the institution you registered with.',
            };
          }
          localStorage.setItem('gripper_token', data.access_token);
          const userPayload = {
            id: data.user_id,
            email: data.email ?? email,
            role: data.role,
            institution_id: data.institution_id,
            graduation_year: data.graduation_year ?? null
          };
          localStorage.setItem('gripper_user', JSON.stringify(userPayload));
          
          set({ 
            token: data.access_token, 
            currentUser: userPayload 
          });

          await get().fetchInstitutions();
          return { ok: true };
        }
        const err = await res.json().catch(() => ({ detail: 'Invalid credentials.' }));
        return {
          ok: false,
          error: typeof err.detail === 'string' ? err.detail : 'Invalid credentials. Check your password, verification status, or institution selection.',
        };
      } catch (err) {
        console.error('Login error', err);
        return { ok: false, error: 'Network connection failed. Is the backend running on port 8000?' };
      } finally {
        set({ isLoading: false });
      }
    },

    register: async (email, password, instId, role, graduationYear) => {
      set({ isLoading: true });
      try {
        const res = await fetch(apiUrl('/auth/register'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Institution-ID': instId
          },
          body: JSON.stringify({
            email,
            password,
            institution_id: instId,
            role,
            graduation_year: graduationYear || null
          })
        });
        if (res.ok) {
          return { success: true };
        } else {
          const data = await res.json();
          return { success: false, error: data.detail || 'Registration failed.' };
        }
      } catch (err) {
        console.error('Registration error', err);
        return { success: false, error: 'Network connection failed.' };
      } finally {
        set({ isLoading: false });
      }
    },

    logout: () => {
      const token = get().token;
      if (token) {
        void fetch(apiUrl('/auth/logout'), {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => undefined);
      }
      localStorage.removeItem('gripper_token');
      localStorage.removeItem('gripper_user');
      set({ 
        token: null, 
        currentUser: null, 
        currentInstitution: null, 
        currentPortfolio: null, 
        holdings: [], 
        violations: [], 
        resolvedViolations: [],
        documents: [],
        simulatedViolations: []
      });
    },

    fetchInstitutions: async () => {
      set({ isLoading: true });
      try {
        const res = await fetch(apiUrl('/institutions'));
        if (res.ok) {
          const data = await res.json();
          // Keep sign-in usable while the API is starting or unavailable. The
          // defaults mirror the backend seed data and are replaced whenever a
          // valid institution response is available.
          const institutions = Array.isArray(data) && data.length > 0
            ? data
            : DEFAULT_INSTITUTIONS;
          set({ institutions });
          
          // Auto-select logged-in user's institution first, or default to first
          const user = get().currentUser;
          if (user) {
            const userInst = institutions.find((i: Institution) => i.id === user.institution_id);
            if (userInst) {
              await get().setInstitution(userInst);
              return;
            }
          }
          if (institutions.length > 0 && !get().currentInstitution) {
            await get().setInstitution(institutions[0]);
          }
        } else {
          set({ institutions: DEFAULT_INSTITUTIONS });
        }
      } catch (err) {
        console.error('Failed to fetch institutions', err);
        set({ institutions: DEFAULT_INSTITUTIONS });
      } finally {
        set({ isLoading: false });
      }
    },

    fetchPortfolios: async (instId) => {
      try {
        const res = await fetch(apiUrl('/portfolios'), {
          headers: getHeaders(instId)
        });
        if (res.ok) {
          const data = await res.json();
          set({ portfolios: data });
          if (data.length > 0) {
            await get().setPortfolio(data[0]);
          }
        }
      } catch (err) {
        console.error('Failed to fetch portfolios', err);
      }
    },

    fetchHoldings: async (portfolioId, instId) => {
      try {
        const res = await fetch(apiUrl(`/portfolios/${portfolioId}/holdings`), {
          headers: getHeaders(instId)
        });
        if (res.ok) {
          const data = await res.json();
          set({ holdings: data });
        }
      } catch (err) {
        console.error('Failed to fetch holdings', err);
      }
    },

    fetchViolations: async (portfolioId, instId) => {
      try {
        const res = await fetch(apiUrl(`/portfolios/${portfolioId}/violations?resolved=false`), {
          headers: getHeaders(instId)
        });
        if (res.ok) {
          const data = await res.json();
          set({ violations: data });
        }
      } catch (err) {
        console.error('Failed to fetch violations', err);
      }
    },

    fetchResolvedViolations: async (portfolioId, instId) => {
      try {
        const res = await fetch(apiUrl(`/portfolios/${portfolioId}/violations?resolved=true`), {
          headers: getHeaders(instId)
        });
        if (res.ok) {
          const data = await res.json();
          set({ resolvedViolations: data });
        }
      } catch (err) {
        console.error('Failed to fetch resolved violations', err);
      }
    },

    fetchDocuments: async (instId) => {
      try {
        const res = await fetch(apiUrl('/documents'), {
          headers: getHeaders(instId)
        });
        if (res.ok) {
          const data = await res.json();
          set({ documents: data });
        }
      } catch (err) {
        console.error('Failed to fetch research documents', err);
      }
    },

    evaluateCompliance: async (portfolioId, instId) => {
      set({ isLoading: true });
      try {
        const res = await fetch(apiUrl(`/portfolios/${portfolioId}/evaluate`), {
          method: 'POST',
          headers: getHeaders(instId)
        });
        if (res.ok) {
          await get().fetchViolations(portfolioId, instId);
          await get().fetchResolvedViolations(portfolioId, instId);
        }
      } catch (err) {
        console.error('Failed to evaluate compliance', err);
      } finally {
        set({ isLoading: false });
      }
    },

    simulateCompliance: async (portfolioId, instId, holdingsData) => {
      set({ isLoading: true });
      try {
        const res = await fetch(apiUrl(`/portfolios/${portfolioId}/simulate`), {
          method: 'POST',
          headers: getHeaders(instId),
          body: JSON.stringify(holdingsData.map(h => ({
            ticker: h.ticker,
            weight: h.weight,
            cost_basis: h.cost_basis,
            conviction_score: h.conviction_score || null
          })))
        });
        if (res.ok) {
          const data = await res.json();
          set({ simulatedViolations: data.violations || [] });
        }
      } catch (err) {
        console.error('Failed to simulate portfolio compliance', err);
      } finally {
        set({ isLoading: false });
      }
    },

    saveHoldings: async (portfolioId, instId, holdingsData) => {
      set({ isLoading: true });
      try {
        const res = await fetch(apiUrl(`/portfolios/${portfolioId}/holdings`), {
          method: 'POST',
          headers: getHeaders(instId),
          body: JSON.stringify(holdingsData.map(h => ({
            ticker: h.ticker,
            weight: h.weight,
            cost_basis: h.cost_basis,
            conviction_score: h.conviction_score || null
          })))
        });
        if (res.ok) {
          await get().evaluateCompliance(portfolioId, instId);
          await get().fetchHoldings(portfolioId, instId);
        }
      } catch (err) {
        console.error('Failed to save holdings', err);
      } finally {
        set({ isLoading: false });
      }
    }
  };
});

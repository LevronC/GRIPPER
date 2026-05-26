import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  LayoutDashboard, 
  ShieldAlert, 
  FileText, 
  Scale, 
  Search, 
  Sparkles, 
  Plus, 
  Trash2, 
  CheckCircle, 
  Database,
  Building,
  Upload,
  Cpu,
  Clock,
  LogOut,
  Lock,
  Mail,
  UserPlus,
  ShieldCheck,
  ChevronRight,
  Fingerprint,
  Zap,
  Activity,
  History,
  Newspaper,
  BarChart3,
  Mic2,
  Play,
  Square,
  Send,
  FastForward,
  Loader2,
  Volume2,
  TrendingUp,
  TrendingDown
} from 'lucide-react';
import { useStore } from '../store/useStore';
import type { Holding, Violation } from '../store/useStore';
import ExplainabilityDrawer from './ExplainabilityDrawer';

// Static metadata of sectors for mapping
const SECTORS = ['Technology', 'Financials', 'Consumer Cyclical', 'Energy', 'Healthcare', 'Communication Services', 'Other'];

const catalystSignals = [
  { name: 'Rate Cut', probability: 65, impact: 'High' },
  { name: 'Earnings Beat', probability: 82, impact: 'Critical' },
  { name: 'Regulatory Review', probability: 24, impact: 'Medium' },
  { name: 'M&A Rumor', probability: 12, impact: 'Low' },
  { name: 'Product Launch', probability: 45, impact: 'High' }
];

const intelligenceStats = [
  { label: 'Net Asset Value', value: '$4.28M', change: '+12.4%', trend: 'up' },
  { label: 'Risk Exposure', value: '32.4%', change: '-2.1%', trend: 'down' },
  { label: 'Alpha Signal', value: '8.42', change: '+0.8', trend: 'up' },
  { label: 'Portfolio Beta', value: '1.08', change: 'Steady', trend: 'neutral' }
];

const initialNewsFeed = [
  {
    id: '1',
    headline: 'SEC announces new disclosure rules for technology infrastructure spend',
    source: 'Bloomberg',
    time: '2m ago',
    content: 'The Securities and Exchange Commission adopted new rules intended to enhance transparency for infrastructure expenditures across major technology platforms.'
  },
  {
    id: '2',
    headline: 'Global chip shortage intensifies after major fabrication plant disruption',
    source: 'Reuters',
    time: '15m ago',
    content: 'A semiconductor manufacturing facility in East Asia reported a serious disruption, potentially constraining supply chains for the next two quarters.'
  },
  {
    id: '3',
    headline: 'CEO of major logistics provider steps down unexpectedly',
    source: 'WSJ',
    time: '45m ago',
    content: 'The chief executive officer of a large logistics firm announced an immediate resignation, creating near-term continuity and governance concerns.'
  }
];

const sampleFiling = `ITEM 1. BUSINESS
Axiom Dynamics Inc. is a global leader in institutional risk modeling and catalyst prediction.
Capital expenditures for fiscal year 2026 were $1.2 billion, primarily driven by proprietary data centers.
For fiscal year 2027, the company anticipates approximately $1.8 billion in CapEx for distributed job clusters and low-latency inference pipelines.`;

type RiskResult = {
  level: 'low' | 'medium' | 'high';
  categories: string[];
  justification: string;
};

type NewsItem = (typeof initialNewsFeed)[number] & { risk?: RiskResult };

type SearchResult = {
  company: string;
  sector: string;
  similarity: number;
  page: number;
  content: string;
};

export default function GripperDashboard() {
  const {
    token,
    currentUser,
    institutions,
    currentInstitution,
    currentPortfolio,
    holdings,
    violations,
    resolvedViolations,
    documents,
    simulatedViolations,
    activeTab,
    isLoading,
    setActiveTab,
    fetchInstitutions,
    evaluateCompliance,
    saveHoldings,
    login,
    register,
    logout,
    simulateCompliance,
    fetchDocuments
  } = useStore();

  const [selectedViolation, setSelectedViolation] = useState<Violation | null>(null);

  // Ingestion Hub state
  const [sector, setSector] = useState('Technology');
  const [company, setCompany] = useState('');
  const [recommendation, setRecommendation] = useState('buy');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<{ type: 'success' | 'error' | null, msg: string }>({ type: null, msg: '' });

  // Semantic Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const searchLimit = 3;
  const [isSearching, setIsSearching] = useState(false);

  // Editable Holdings state (local copy for draft edits)
  const [holdingsDraft, setHoldingsDraft] = useState<Holding[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [newWeight, setNewWeight] = useState(5);
  const [newCostBasis, setNewCostBasis] = useState(100);

  // Auth local state
  const [authMode, setAuthMode] = useState<'login' | 'register' | 'verify'>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authInstId, setAuthInstId] = useState('');
  const [authRole, setAuthRole] = useState('analyst');
  const [authGradYear, setAuthGradYear] = useState<number | ''>('');
  const [authCode, setAuthCode] = useState('');
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');

  // Sandbox simulation local state
  const [simulationActive, setSimulationActive] = useState(false);
  const [simulationTriggered, setSimulationTriggered] = useState(false);

  // Intelligence center local state. These are frontend-only simulations adapted from the reference app.
  const [newsFeed, setNewsFeed] = useState<NewsItem[]>(initialNewsFeed);
  const [analyzingNewsId, setAnalyzingNewsId] = useState<string | null>(null);
  const [secQuestion, setSecQuestion] = useState('');
  const [secAnswer, setSecAnswer] = useState<string | null>(null);
  const [secLoading, setSecLoading] = useState(false);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);

  // Load initial institutions
  useEffect(() => {
    fetchInstitutions();
  }, [fetchInstitutions]);

  // Update holdings draft when global holdings change
  useEffect(() => {
    // The matrix is an editable draft; reset it when backend holdings change.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHoldingsDraft(holdings);
  }, [holdings]);

  const selectedAuthInstId = authInstId || institutions[0]?.id || '';

  // Poll document ingestion progress periodically if there are pending docs
  useEffect(() => {
    if (!token || !currentInstitution) return;
    
    // Initial fetch
    fetchDocuments(currentInstitution.id);

    const interval = setInterval(() => {
      fetchDocuments(currentInstitution.id);
    }, 4000);

    return () => clearInterval(interval);
  }, [token, currentInstitution, fetchDocuments]);

  // Handle Auth submission
  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');

    if (authMode === 'login') {
      if (!selectedAuthInstId) {
        setAuthError('Please select an institution context.');
        return;
      }
      const ok = await login(authEmail, authPassword, selectedAuthInstId);
      if (!ok) {
        setAuthError('Invalid credentials. Check your password, verification status, or institution selection.');
      }
    } else if (authMode === 'register') {
      if (!selectedAuthInstId) {
        setAuthError('Please select an institution context.');
        return;
      }
      const res = await register(
        authEmail, 
        authPassword, 
        selectedAuthInstId, 
        authRole, 
        authGradYear === '' ? undefined : authGradYear
      );
      if (res.success) {
        setAuthSuccess('Registration successful! Check your .edu email for the verification code.');
        setAuthMode('verify');
      } else {
        setAuthError(res.error || 'Registration failed. Make sure the email ends in .edu and is unique.');
      }
    } else {
      // Verification mode
      try {
        const res = await fetch('http://localhost:8000/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: authEmail, code: authCode })
        });
        if (res.ok) {
          setAuthSuccess('Verification successful! You can now log in.');
          setAuthMode('login');
          setAuthPassword('');
        } else {
          const data = await res.json();
          setAuthError(data.detail || 'Verification failed.');
        }
      } catch {
        setAuthError('Network error during verification.');
      }
    }
  };

  // Handle document upload
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !currentInstitution) {
      setUploadStatus({ type: 'error', msg: 'Please select a file and institution.' });
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('sector', sector);
    formData.append('company', company || selectedFile.name.replace('.pdf', ''));
    formData.append('recommendation', recommendation);

    try {
      setUploadStatus({ type: 'success', msg: 'Uploading...' });
      const res = await fetch('http://localhost:8000/documents/upload', {
        method: 'POST',
        headers: {
          'X-Institution-ID': currentInstitution.id,
          'Authorization': `Bearer ${token || ''}`
        },
        body: formData
      });

      if (res.ok) {
        setUploadStatus({ type: 'success', msg: 'Document uploaded successfully! Ingestion queued.' });
        fetchDocuments(currentInstitution.id);
        setCompany('');
        setSelectedFile(null);
      } else {
        const err = await res.json();
        setUploadStatus({ type: 'error', msg: err.detail || 'Upload failed.' });
      }
    } catch {
      setUploadStatus({ type: 'error', msg: 'Network failure during upload.' });
    }
  };

  // Handle semantic search
  const handleSemanticSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim() || !currentInstitution) return;

    setIsSearching(true);
    try {
      const res = await fetch('http://localhost:8000/search/semantic', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Institution-ID': currentInstitution.id,
          'Authorization': `Bearer ${token || ''}`
        },
        body: JSON.stringify({
          query: searchQuery,
          limit: searchLimit
        })
      });

      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results || []);
      } else {
        console.error('Search failed');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  };

  // Run Sandbox simulation
  const handleSandboxSimulate = async () => {
    if (!currentPortfolio || !currentInstitution) return;
    setSimulationTriggered(true);
    await simulateCompliance(currentPortfolio.id, currentInstitution.id, holdingsDraft);
  };

  const handleAnalyzeNews = async (id: string, content: string) => {
    setAnalyzingNewsId(id);
    await new Promise((resolve) => setTimeout(resolve, 650));
    const normalized = content.toLowerCase();
    const result: RiskResult = normalized.includes('disruption') || normalized.includes('shortage')
      ? {
          level: 'high',
          categories: ['Supply Chain', 'Concentration Risk'],
          justification: 'The event can impair revenue assumptions for hardware and semiconductor holdings with concentrated supplier exposure.'
        }
      : normalized.includes('sec') || normalized.includes('disclosure')
        ? {
            level: 'medium',
            categories: ['Regulatory', 'Reporting'],
            justification: 'New disclosure obligations may change compliance workload and create near-term headline risk for covered issuers.'
          }
        : {
            level: 'medium',
            categories: ['Governance', 'Key Person'],
            justification: 'Unexpected executive turnover can raise continuity risk until succession plans and investor communications are clear.'
          };

    setNewsFeed((items) => items.map((item) => item.id === id ? { ...item, risk: result } : item));
    setAnalyzingNewsId(null);
  };

  const handleAskSecQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!secQuestion.trim()) return;
    setSecLoading(true);
    setSecAnswer(null);
    await new Promise((resolve) => setTimeout(resolve, 600));
    const question = secQuestion.toLowerCase();
    if (question.includes('capex') || question.includes('capital')) {
      setSecAnswer('CapEx increased from $1.2B in fiscal 2026 to an expected $1.8B in fiscal 2027, a 50% increase tied to data centers, distributed job clusters, and inference infrastructure.');
    } else if (question.includes('risk')) {
      setSecAnswer('The main risk signal is execution intensity: the filing points to heavy infrastructure investment that could pressure margins if expected model and ingestion throughput gains do not arrive.');
    } else {
      setSecAnswer('The filing emphasizes infrastructure expansion for institutional risk modeling, catalyst prediction, and low-latency financial ingestion workflows.');
    }
    setSecLoading(false);
  };

  const handleTranscribe = async () => {
    setTranscribing(true);
    setAudioPlaying(true);
    setTranscript(null);
    await new Promise((resolve) => setTimeout(resolve, 900));
    setTranscript('Management reiterated disciplined capital allocation while noting that demand for low-latency analytics remains resilient. The committee should monitor margin pressure from higher compute spend and watch for confirmation in the next 10-Q.');
    setTranscribing(false);
  };

  const handleStopAudio = () => {
    setAudioPlaying(false);
    setTranscribing(false);
  };

  // Modify holdings locally
  const updateDraftWeight = (index: number, newWeightVal: number) => {
    const updated = [...holdingsDraft];
    updated[index] = { ...updated[index], weight: newWeightVal / 100 };
    setHoldingsDraft(updated);
  };

  const removeDraftHolding = (index: number) => {
    const updated = holdingsDraft.filter((_, i) => i !== index);
    setHoldingsDraft(updated);
  };

  const addDraftHolding = () => {
    if (!newTicker.trim()) return;
    const item: Holding = {
      ticker: newTicker.toUpperCase().trim(),
      weight: newWeight / 100,
      cost_basis: newCostBasis
    };
    setHoldingsDraft([...holdingsDraft, item]);
    setNewTicker('');
  };

  const commitHoldings = async () => {
    if (!currentPortfolio || !currentInstitution) return;
    await saveHoldings(currentPortfolio.id, currentInstitution.id, holdingsDraft);
    setSimulationActive(false);
    setSimulationTriggered(false);
  };

  // Calculate stats
  const totalHoldingsWeight = holdings.reduce((sum, h) => sum + h.weight, 0);
  const activeAlertsCount = violations.length;
  const complianceScore = Math.max(0, 100 - activeAlertsCount * 15);

  // Render helpers
  const getSeverityBadge = (sev: string) => {
    if (sev === 'critical') {
      return 'bg-red-500/10 text-red-400 border-red-500/25';
    }
    return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/25';
  };

  // AUTH SCREEN COMPONENT
  if (!token) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#05070A] font-sans text-slate-100 relative overflow-hidden">
        {/* Glowing background highlights inspired by high-end dashboards */}
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-cyan-600/10 blur-[150px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] rounded-full bg-blue-600/10 blur-[150px]" />

        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }} 
          animate={{ opacity: 1, scale: 1 }} 
          transition={{ duration: 0.4 }}
          className="w-full max-w-[420px] bg-[#0A0D14]/90 backdrop-blur-3xl border border-white/5 p-10 rounded-[2.5rem] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)] z-10"
        >
          {/* Logo and title */}
          <div className="text-center mb-10">
            <motion.div 
              whileHover={{ rotate: 180 }}
              transition={{ duration: 0.8 }}
              className="mx-auto w-16 h-16 bg-gradient-to-tr from-cyan-500 to-blue-600 rounded-3xl flex items-center justify-center shadow-[0_0_30px_-5px_rgba(34,211,238,0.3)] mb-6"
            >
              <Fingerprint size={32} className="text-white" />
            </motion.div>
            <h2 className="text-3xl font-black tracking-tighter text-white mb-2">
              GRIPPER<span className="text-cyan-400 font-normal">.terminal</span>
            </h2>
            <p className="text-xs text-slate-500 font-medium uppercase tracking-[0.2em]">
              Security & Compliance Vault
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleAuthSubmit} className="space-y-5">
            <AnimatePresence mode="wait">
              {authMode !== 'verify' ? (
                <motion.div
                  key="main-auth"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  className="space-y-4"
                >
                  {/* Institution dropdown */}
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1">
                      <Building size={12} className="text-cyan-500/70" />
                      Infrastructure Node
                    </label>
                    <select
                      value={selectedAuthInstId}
                      onChange={(e) => setAuthInstId(e.target.value)}
                      className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-3 px-4 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 transition-all appearance-none cursor-pointer"
                    >
                      {institutions.map((inst) => (
                        <option key={inst.id} value={inst.id} className="bg-[#0A0D14]">
                          {inst.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Email input */}
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1">
                      <Mail size={12} className="text-cyan-500/70" />
                      Academic ID (.edu)
                    </label>
                    <input
                      type="email"
                      required
                      value={authEmail}
                      onChange={(e) => setAuthEmail(e.target.value)}
                      placeholder="analyst@stetson.edu"
                      className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-3 px-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 transition-all"
                    />
                  </div>

                  {/* Password input */}
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1">
                      <Lock size={12} className="text-cyan-500/70" />
                      Encryption Key
                    </label>
                    <input
                      type="password"
                      required
                      value={authPassword}
                      onChange={(e) => setAuthPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-3 px-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 transition-all"
                    />
                  </div>

                  {authMode === 'register' && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }} 
                      animate={{ opacity: 1, height: 'auto' }} 
                      className="space-y-4 pt-1"
                    >
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1">
                          <UserPlus size={12} className="text-cyan-500/70" />
                          Clearance Level
                        </label>
                        <select
                          value={authRole}
                          onChange={(e) => setAuthRole(e.target.value)}
                          className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-3 px-4 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 appearance-none transition-all cursor-pointer"
                        >
                          <option value="analyst" className="bg-[#0A0D14]">Research Analyst</option>
                          <option value="sector_lead" className="bg-[#0A0D14]">Sector Lead</option>
                          <option value="pm" className="bg-[#0A0D14]">Portfolio Manager (PM)</option>
                          <option value="admin" className="bg-[#0A0D14]">Systems Administrator</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1">
                          <CheckCircle size={12} className="text-cyan-500/70" />
                          Graduation Year
                        </label>
                        <input
                          type="number"
                          min="2024"
                          max="2045"
                          value={authGradYear}
                          onChange={(e) => setAuthGradYear(e.target.value === '' ? '' : Number(e.target.value))}
                          placeholder="2027"
                          className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-3 px-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 transition-all"
                        />
                      </div>
                    </motion.div>
                  )}
                </motion.div>
              ) : (
                <motion.div
                  key="verify-auth"
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  className="space-y-4"
                >
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1">
                      <ShieldCheck size={12} className="text-cyan-500/70" />
                      Verification Code
                    </label>
                    <input
                      type="text"
                      required
                      maxLength={6}
                      value={authCode}
                      onChange={(e) => setAuthCode(e.target.value)}
                      placeholder="000000"
                      className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-4 px-4 text-center text-2xl font-black tracking-[0.5em] text-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 transition-all"
                    />
                    <p className="text-[10px] text-center text-slate-500 mt-2">
                      Enter the 6-digit code sent to your .edu account.
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {authError && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 bg-red-500/5 border border-red-500/20 text-red-400 rounded-2xl text-[11px] font-medium leading-relaxed">
                {authError}
              </motion.div>
            )}

            {authSuccess && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 bg-cyan-500/5 border border-cyan-500/20 text-cyan-400 rounded-2xl text-[11px] font-medium leading-relaxed">
                {authSuccess}
              </motion.div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-4 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white rounded-2xl text-sm font-black tracking-wide transition-all shadow-[0_20px_40px_-10px_rgba(8,145,178,0.3)] cursor-pointer flex items-center justify-center gap-3 active:scale-[0.98]"
            >
              {isLoading ? (
                <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  {authMode === 'login' ? 'ESTABLISH LINK' : authMode === 'register' ? 'CREATE SECURE NODE' : 'VERIFY IDENTITY'}
                  <ChevronRight size={18} />
                </>
              )}
            </button>
          </form>

          {/* Switcher */}
          <div className="text-center mt-8">
            <button
              type="button"
              onClick={() => {
                setAuthMode(authMode === 'login' ? 'register' : 'login');
                setAuthError('');
                setAuthSuccess('');
              }}
              className="text-[11px] text-slate-500 hover:text-cyan-400 font-bold tracking-wider transition-colors uppercase"
            >
              {authMode === 'login' 
                ? "Request New Access Node" 
                : 'Already have credentials? Link Hub'}
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  // MAIN DASHBOARD LAYOUT
  return (
    <div className="flex h-screen bg-[#05070A] font-sans text-slate-200 overflow-hidden">
      {/* Sidebar Navigation */}
      <aside className="w-80 bg-[#0A0D14]/80 backdrop-blur-3xl border-r border-white/5 p-8 flex flex-col z-20">
        
        {/* Title */}
        <div className="flex items-center gap-3 mb-10 group">
          <div className="bg-gradient-to-tr from-cyan-500 to-blue-600 p-2.5 rounded-[1rem] shadow-[0_0_20px_-5px_rgba(34,211,238,0.2)]">
            <Fingerprint size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tighter text-white group-hover:text-cyan-400 transition-colors">GRIPPER</h1>
            <p className="text-[9px] text-slate-500 font-black tracking-[0.3em] uppercase opacity-60">Security Terminal</p>
          </div>
        </div>

        {/* Tenant Status */}
        <div className="mb-10 p-5 bg-white/[0.02] border border-white/5 rounded-3xl space-y-4">
          <div className="flex justify-between items-center">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2">
              <Zap size={12} className="text-cyan-500/70" />
              Active Context
            </span>
            <div className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          </div>
          
          <div className="space-y-1">
            <h3 className="text-sm font-black text-white truncate">{currentInstitution?.name}</h3>
            <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">{currentPortfolio?.name || 'Loading Portfolio...'}</p>
          </div>

          <div className="pt-4 border-t border-white/5 flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[9px] text-slate-600 font-black uppercase">Graduation Year</span>
              <span className="text-xs font-mono font-bold text-slate-300">{currentUser?.graduation_year || 'N/A'}</span>
            </div>
            <div className="flex flex-col items-end text-right">
              <span className="text-[9px] text-slate-600 font-black uppercase">Clearance</span>
              <span className="text-xs font-mono font-bold text-cyan-400 uppercase">{currentUser?.role}</span>
            </div>
          </div>
        </div>

        {/* Nav Tabs */}
        <nav className="flex-1 space-y-2">
          {[
            { id: 'Dashboard', label: 'Compliance Hub', icon: Activity },
            { id: 'Intelligence', label: 'Intelligence Center', icon: LayoutDashboard },
            { id: 'Portfolio', label: 'Portfolio Matrix', icon: Scale },
            { id: 'SEC Ingestion', label: 'Ingestion Pipeline', icon: Upload },
            { id: 'Institutional Memory', label: 'Neural Search', icon: Search },
            { id: 'Earnings', label: 'Earnings Terminal', icon: Mic2 }
          ].map((item) => {
            const isActive = activeTab === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-4 px-5 py-4 rounded-2xl font-bold text-[13px] tracking-wide transition-all duration-300 border ${
                  isActive 
                    ? 'bg-cyan-500/5 text-cyan-400 border-cyan-500/20 shadow-[0_10px_20px_-10px_rgba(34,211,238,0.1)]' 
                    : 'text-slate-500 border-transparent hover:bg-white/[0.03] hover:text-slate-300'
                }`}
              >
                <Icon size={18} className={isActive ? 'text-cyan-400' : 'text-slate-600'} />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* User Badge */}
        <div className="mt-auto pt-8 border-t border-white/5 flex items-center gap-4 group">
          <div className="h-12 w-12 shrink-0 rounded-[1.25rem] bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center font-black text-lg text-white shadow-xl shadow-cyan-900/10">
            {currentUser?.email.slice(0, 1).toUpperCase() || 'G'}
          </div>
          <div className="flex-1 min-w-0">
            <h5 className="text-xs font-black text-white truncate group-hover:text-cyan-400 transition-colors">{currentUser?.email}</h5>
            <p className="text-[10px] text-slate-500 font-black tracking-widest uppercase mt-0.5">Verified Academic</p>
          </div>
          <button 
            onClick={logout}
            className="p-2.5 rounded-xl bg-white/[0.03] hover:bg-red-500/10 text-slate-600 hover:text-red-400 border border-white/5 hover:border-red-500/20 transition-all cursor-pointer"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* Main Terminal Content */}
      <main className="flex-1 overflow-y-auto p-12 relative bg-[#05070A]">
        {/* Header Section */}
        <header className="flex justify-between items-end mb-12">
          <div className="space-y-1">
            <div className="flex items-center gap-2 mb-2">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
              <p className="text-[10px] text-cyan-400/70 font-black uppercase tracking-[0.3em]">Grid Access Verified</p>
            </div>
            <h1 className="text-4xl font-black tracking-tighter text-white">{activeTab}</h1>
          </div>

          <div className="flex gap-4">
            <button
              type="button"
              onClick={() => {
                if (!currentPortfolio || !currentInstitution) return;
                evaluateCompliance(currentPortfolio.id, currentInstitution.id);
              }}
              disabled={isLoading || !currentPortfolio || !currentInstitution}
              className="px-6 py-3.5 bg-white/[0.03] hover:bg-white/[0.08] border border-white/10 rounded-2xl text-[11px] font-black uppercase tracking-widest transition-all flex items-center gap-3 cursor-pointer disabled:opacity-50 active:scale-95"
            >
              <History size={14} className="text-cyan-400" />
              Execute Compliance Audit
            </button>
          </div>
        </header>

        {/* Tab Content Rendering */}
        <div className="max-w-7xl mx-auto">
          {activeTab === 'Dashboard' && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
              {/* Stats Grid */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {[
                  { label: 'Integrity Index', value: `${complianceScore}%`, color: 'text-cyan-400', bg: 'bg-cyan-500' },
                  { label: 'System Breaches', value: activeAlertsCount, color: activeAlertsCount > 0 ? 'text-red-400' : 'text-slate-400', bg: 'bg-red-500' },
                  { label: 'Neutralized Risks', value: resolvedViolations.length, color: 'text-emerald-400', bg: 'bg-emerald-500' },
                  { label: 'Portfolio Weight', value: `${(totalHoldingsWeight * 100).toFixed(0)}%`, color: 'text-white', bg: 'bg-blue-500' }
                ].map((stat, i) => (
                  <div key={i} className="bg-[#0A0D14] border border-white/5 p-8 rounded-[2rem] space-y-4">
                    <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest block">{stat.label}</span>
                    <div className="text-4xl font-black tracking-tighter transition-colors font-mono">{stat.value}</div>
                    <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
                      <div className={`${stat.bg} h-full transition-all duration-700`} style={{ width: typeof stat.value === 'string' ? stat.value : `${Math.min(100, (Number(stat.value)/10)*100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              {/* Main Sections */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-8">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-black text-white tracking-tight flex items-center gap-3">
                      <ShieldAlert size={20} className="text-red-500" />
                      Active Governance Breaches
                    </h3>
                  </div>
                  
                  {violations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-24 border border-dashed border-white/5 rounded-[2rem] space-y-6 bg-white/[0.01]">
                      <div className="h-16 w-16 bg-cyan-500/10 rounded-full flex items-center justify-center">
                        <ShieldCheck size={32} className="text-cyan-400" />
                      </div>
                      <div className="text-center space-y-2">
                        <p className="text-xs font-black text-white uppercase tracking-widest">Shield Integrity 100%</p>
                        <p className="text-[11px] text-slate-500 max-w-[280px] font-medium leading-relaxed">
                          All institutional assets are within IPS safety thresholds. Neural grid is stable.
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {violations.map((v) => (
                        <div key={v.id} className="p-6 bg-white/[0.02] border border-white/5 hover:border-cyan-500/30 rounded-[1.5rem] flex flex-col md:flex-row justify-between items-start md:items-center gap-6 transition-all group">
                          <div className="space-y-2">
                            <div className="flex items-center gap-3">
                              <span className={`text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-full border ${getSeverityBadge(v.severity)}`}>
                                {v.severity}
                              </span>
                              <span className="text-sm font-black text-white tracking-tight">
                                {v.event_type.replace(/_/g, ' ').toUpperCase()}
                              </span>
                            </div>
                            <p className="text-xs text-slate-500 font-medium leading-relaxed max-w-lg group-hover:text-slate-400 transition-colors">
                              {v.details.message}
                            </p>
                          </div>
                          <button
                            onClick={() => setSelectedViolation(v)}
                            className="px-6 py-2.5 bg-cyan-500/10 hover:bg-cyan-500 border border-cyan-500/20 hover:border-cyan-500 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-cyan-400 hover:text-[#05070A] transition-all flex items-center gap-2 cursor-pointer shadow-lg active:scale-95"
                          >
                            <Sparkles size={12} />
                            Neural RAG
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-8">
                  <h3 className="text-lg font-black text-white tracking-tight flex items-center gap-3">
                    <Clock size={20} className="text-cyan-400" />
                    Audit Log
                  </h3>
                  <div className="space-y-6 max-h-[500px] overflow-y-auto pr-4 scrollbar-hide">
                    {[...violations, ...resolvedViolations].sort((a,b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).map((v, i) => (
                      <div key={v.id} className="flex gap-4 relative">
                        <div className="flex flex-col items-center">
                          <div className={`h-2.5 w-2.5 rounded-full z-10 ${v.resolved ? 'bg-cyan-400' : 'bg-red-500'}`} />
                          {i !== (violations.length + resolvedViolations.length - 1) && <div className="w-[1px] bg-white/5 flex-1 my-1" />}
                        </div>
                        <div className="pb-6">
                          <span className={`text-[10px] font-black uppercase tracking-widest ${v.resolved ? 'text-cyan-400' : 'text-red-500'}`}>
                            {v.resolved ? 'NEUTRALIZED' : 'BREACH DETECTED'}
                          </span>
                          <h4 className="text-xs font-black text-slate-300 mt-1 uppercase tracking-tight">{v.event_type.replace(/_/g, ' ')}</h4>
                          <span className="block text-[9px] text-slate-600 font-bold mt-1 uppercase tracking-widest">{new Date(v.created_at).toLocaleTimeString()}</span>
                          <p className="text-[10px] text-slate-500 font-medium leading-relaxed mt-2 italic">"{v.details.message}"</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'Intelligence' && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {intelligenceStats.map((stat) => {
                  const Icon = stat.trend === 'up' ? TrendingUp : stat.trend === 'down' ? TrendingDown : Activity;
                  return (
                    <div key={stat.label} className="bg-[#0A0D14] border border-white/5 p-6 rounded-[2rem] group hover:border-cyan-500/20 transition-all">
                      <div className="flex justify-between items-start mb-3">
                        <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">{stat.label}</span>
                        <Icon size={16} className={stat.trend === 'down' ? 'text-red-400' : stat.trend === 'up' ? 'text-emerald-400' : 'text-cyan-400'} />
                      </div>
                      <div className="flex items-end gap-2">
                        <span className="text-3xl font-black font-mono text-white group-hover:text-cyan-400 transition-colors">{stat.value}</span>
                        <span className={`text-[10px] font-black pb-1 ${stat.trend === 'down' ? 'text-red-400' : stat.trend === 'up' ? 'text-emerald-400' : 'text-slate-500'}`}>{stat.change}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-8">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-black text-white tracking-tight flex items-center gap-3">
                        <BarChart3 size={20} className="text-cyan-400" />
                        Market Catalyst Probability
                      </h3>
                      <p className="text-[10px] text-slate-500 mt-2 font-black uppercase tracking-widest">Predictive signal monitor</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                      <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">Ingesting</span>
                    </div>
                  </div>
                  <div className="space-y-5">
                    {catalystSignals.map((signal) => (
                      <div key={signal.name} className="grid grid-cols-[120px_1fr_72px] items-center gap-5">
                        <span className="text-xs font-black text-slate-300">{signal.name}</span>
                        <div className="h-5 bg-white/[0.03] rounded-full overflow-hidden border border-white/5">
                          <div
                            className={`h-full rounded-full ${signal.probability > 60 ? 'bg-emerald-400' : 'bg-cyan-500'}`}
                            style={{ width: `${signal.probability}%` }}
                          />
                        </div>
                        <div className="text-right">
                          <span className="block text-sm font-black font-mono text-white">{signal.probability}%</span>
                          <span className="block text-[8px] text-slate-600 font-black uppercase">{signal.impact}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-8 space-y-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
                      <Newspaper size={16} className="text-cyan-400" />
                      Risk Feed
                    </h3>
                    <span className="text-[9px] font-black text-slate-500 border border-white/10 rounded-full px-3 py-1 uppercase">Live</span>
                  </div>
                  <div className="space-y-4">
                    {newsFeed.map((item) => (
                      <div key={item.id} className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-cyan-500/20 transition-all">
                        <div className="flex justify-between gap-4 mb-2">
                          <span className="text-[9px] font-black text-cyan-400/70 uppercase tracking-widest">{item.source} / {item.time}</span>
                          {!item.risk && (
                            <button
                              onClick={() => handleAnalyzeNews(item.id, item.content)}
                              disabled={analyzingNewsId === item.id}
                              className="text-[9px] font-black text-emerald-400 uppercase tracking-widest disabled:opacity-50"
                            >
                              {analyzingNewsId === item.id ? 'Auditing...' : 'Audit'}
                            </button>
                          )}
                        </div>
                        <h4 className="text-xs font-black text-slate-200 leading-relaxed">{item.headline}</h4>
                        {item.risk && (
                          <div className="mt-3 pt-3 border-t border-white/5 space-y-2">
                            <div className="flex flex-wrap gap-2">
                              {item.risk.categories.map((category) => (
                                <span key={category} className={`px-2 py-1 rounded-lg text-[8px] font-black uppercase tracking-widest border ${item.risk?.level === 'high' ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
                                  {category}
                                </span>
                              ))}
                            </div>
                            <p className="text-[11px] text-slate-500 leading-relaxed">{item.risk.justification}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="lg:col-span-3 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-black text-white tracking-tight flex items-center gap-3">
                      <FileText size={20} className="text-cyan-400" />
                      SEC Intelligence Engine
                    </h3>
                    <span className="text-[10px] font-mono text-slate-500 bg-white/[0.03] px-3 py-1.5 rounded-xl border border-white/5">DOC_ID: 10K-AXIOM-2026</span>
                  </div>
                  <div className="p-5 rounded-2xl bg-[#05070A] border border-white/5 font-mono text-xs leading-relaxed text-slate-400 whitespace-pre-line max-h-44 overflow-y-auto">
                    <span className="text-cyan-400 font-black">DOCUMENT PREVIEW:</span>{'\n'}{sampleFiling}
                  </div>
                  <form onSubmit={handleAskSecQuestion} className="flex gap-4">
                    <input
                      value={secQuestion}
                      onChange={(e) => setSecQuestion(e.target.value)}
                      placeholder="Ask about CapEx, risks, or guidance..."
                      className="flex-1 bg-white/[0.03] border border-white/10 rounded-2xl py-4 px-5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                    />
                    <button type="submit" disabled={secLoading} className="px-6 py-4 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-2xl transition-all">
                      {secLoading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
                    </button>
                  </form>
                  {secAnswer && (
                    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="p-5 rounded-2xl bg-emerald-500/5 border border-emerald-500/20">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">AI Insights Response</span>
                      </div>
                      <p className="text-sm text-slate-300 leading-relaxed">{secAnswer}</p>
                    </motion.div>
                  )}
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'Portfolio' && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-10">
                <div className="flex justify-between items-center pb-6 border-b border-white/5">
                  <h3 className="text-xl font-black text-white tracking-tight uppercase">Weight Matrix</h3>
                  <div className="text-[10px] font-black text-slate-500 tracking-[0.2em] uppercase">
                    System Saturation: <span className={`font-mono ${totalHoldingsWeight > 1.0 ? 'text-red-500' : 'text-cyan-400'}`}>{(totalHoldingsWeight * 100).toFixed(1)}%</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-white/[0.02] p-6 rounded-[2rem] border border-white/5 items-end">
                  <div className="space-y-2">
                    <label className="text-[9px] font-black text-slate-600 uppercase tracking-widest px-1">Asset Ticker</label>
                    <input
                      type="text"
                      value={newTicker}
                      onChange={(e) => setNewTicker(e.target.value)}
                      placeholder="NVDA"
                      className="w-full bg-[#05070A] border border-white/10 rounded-xl py-2.5 px-4 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[9px] font-black text-slate-600 uppercase tracking-widest px-1">Weight (%)</label>
                    <input
                      type="number"
                      value={newWeight}
                      onChange={(e) => setNewWeight(Number(e.target.value))}
                      placeholder="10"
                      className="w-full bg-[#05070A] border border-white/10 rounded-xl py-2.5 px-4 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[9px] font-black text-slate-600 uppercase tracking-widest px-1">Cost Basis ($)</label>
                    <input
                      type="number"
                      value={newCostBasis}
                      onChange={(e) => setNewCostBasis(Number(e.target.value))}
                      placeholder="120"
                      className="w-full bg-[#05070A] border border-white/10 rounded-xl py-2.5 px-4 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                    />
                  </div>
                  <button onClick={addDraftHolding} className="w-full bg-cyan-600 hover:bg-cyan-500 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-lg shadow-cyan-900/10 cursor-pointer">
                    <span className="inline-flex items-center justify-center gap-2"><Plus size={14} /> Integrate</span>
                  </button>
                </div>

                <div className="space-y-3 max-h-[400px] overflow-y-auto pr-4 scrollbar-hide">
                  {holdingsDraft.map((h, i) => (
                    <div key={i} className="p-6 bg-white/[0.01] border border-white/5 rounded-[1.5rem] flex items-center gap-8 group hover:bg-white/[0.03] transition-all">
                      <div className="w-24">
                        <span className="text-sm font-black font-mono text-white group-hover:text-cyan-400 transition-colors">{h.ticker}</span>
                        <span className="block text-[8px] text-slate-600 font-black uppercase tracking-tighter mt-1">Asset ID: {i+100}</span>
                      </div>
                      <div className="flex-1 space-y-2">
                        <input type="range" min="0" max="50" value={Math.round(h.weight * 100)} onChange={(e) => updateDraftWeight(i, parseInt(e.target.value))} className="w-full h-1 bg-white/5 rounded-full appearance-none accent-cyan-400" />
                        <div className="flex justify-between text-[9px] font-black text-slate-600 uppercase">
                          <span>Allocation Threshold</span>
                          <span className="text-cyan-400">{Math.round(h.weight * 100)}%</span>
                        </div>
                      </div>
                      <div className="w-24 text-right">
                        <span className="text-[9px] text-slate-600 font-black uppercase block">Basis</span>
                        <span className="text-sm font-mono font-black text-white">${h.cost_basis}</span>
                      </div>
                      <button onClick={() => removeDraftHolding(i)} className="text-slate-700 hover:text-red-500 p-2 transition-colors cursor-pointer"><Trash2 size={16} /></button>
                    </div>
                  ))}
                </div>

                <div className="pt-8 border-t border-white/5 flex justify-between items-center">
                  <button onClick={() => setSimulationActive(!simulationActive)} className={`px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all ${simulationActive ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' : 'bg-white/[0.02] text-slate-500 hover:text-slate-300'}`}>
                    {simulationActive ? 'Disable Scenario' : 'Hypothetical Sandbox'}
                  </button>
                  {simulationActive && (
                    <button onClick={handleSandboxSimulate} disabled={isLoading} className="px-6 py-3 rounded-2xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-black uppercase tracking-widest disabled:opacity-50">
                      Run Simulation
                    </button>
                  )}
                  <button onClick={commitHoldings} disabled={isLoading} className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-black py-4 px-10 rounded-2xl text-[11px] uppercase tracking-widest transition-all shadow-xl shadow-cyan-900/20 disabled:opacity-50 cursor-pointer active:scale-95">
                    Commit Changeset
                  </button>
                </div>
                {simulationTriggered && (
                  <div className={`p-5 rounded-2xl border text-xs font-bold ${simulatedViolations.length > 0 ? 'bg-red-500/5 border-red-500/20 text-red-300' : 'bg-emerald-500/5 border-emerald-500/20 text-emerald-300'}`}>
                    {simulatedViolations.length > 0
                      ? `${simulatedViolations.length} hypothetical breach${simulatedViolations.length === 1 ? '' : 'es'} detected before commit.`
                      : 'Simulation completed with no hypothetical breaches.'}
                  </div>
                )}
              </div>

              {/* Sector Exposure Chart */}
              <div className="bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-10">
                <div>
                  <h3 className="text-xl font-black text-white tracking-tight uppercase">Exposures</h3>
                  <p className="text-[10px] text-slate-500 mt-2 font-black tracking-widest uppercase">Grid Saturation Monitor</p>
                </div>
                <div className="space-y-6">
                  {SECTORS.map((sec) => {
                    const secWeight = holdings.reduce((sum, h) => {
                      let mapSec = 'Other';
                      if (['AAPL', 'MSFT', 'NVDA', 'MCRT'].includes(h.ticker)) mapSec = 'Technology';
                      else if (['GOOGL', 'META'].includes(h.ticker)) mapSec = 'Communication Services';
                      else if (['AMZN', 'TSLA'].includes(h.ticker)) mapSec = 'Consumer Cyclical';
                      else if (['XOM', 'CVX'].includes(h.ticker)) mapSec = 'Energy';
                      else if (['JPM', 'BAC', 'GCAP'].includes(h.ticker)) mapSec = 'Financials';
                      else if (['JNJ', 'LLY'].includes(h.ticker)) mapSec = 'Healthcare';
                      return mapSec === sec ? sum + h.weight : sum;
                    }, 0);
                    const pct = secWeight * 100;
                    const limit = 30.0;
                    const isBreached = pct > limit;
                    return (
                      <div key={sec} className="space-y-3">
                        <div className="flex justify-between text-[10px] font-black uppercase tracking-widest">
                          <span className="text-slate-500">{sec}</span>
                          <span className={isBreached ? 'text-red-500' : 'text-cyan-400'}>{pct.toFixed(1)}% / {limit}%</span>
                        </div>
                        <div className="h-1.5 w-full bg-white/[0.03] rounded-full overflow-hidden relative">
                          <div className={`h-full transition-all duration-1000 ${isBreached ? 'bg-red-500 shadow-[0_0_15px_rgba(239,68,68,0.5)]' : 'bg-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.3)]'}`} style={{ width: `${Math.min(100, (pct / 100) * 100)}%` }} />
                          <div className="absolute top-0 bottom-0 left-[30%] w-[1px] bg-red-500/40 z-10" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'SEC Ingestion' && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-10">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-cyan-500/10 rounded-2xl"><Upload className="text-cyan-400" size={24} /></div>
                  <h3 className="text-2xl font-black text-white tracking-tight uppercase">Neural Ingestion Pipeline</h3>
                </div>
                <form onSubmit={handleUpload} className="space-y-8">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest px-1">Target Entity / Ticker</label>
                      <input type="text" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Tesla (TSLA)" required className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-4 px-5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all" />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest px-1">Sector Classification</label>
                      <select value={sector} onChange={(e) => setSector(e.target.value)} className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-4 px-5 text-sm text-white focus:outline-none appearance-none cursor-pointer">
                        {SECTORS.map(s => <option key={s} value={s} className="bg-[#0A0D14]">{s}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest px-1">Analytical Sentiment</label>
                    <select value={recommendation} onChange={(e) => setRecommendation(e.target.value)} className="w-full bg-white/[0.03] border border-white/10 rounded-2xl py-4 px-5 text-sm text-white focus:outline-none appearance-none cursor-pointer">
                      <option value="buy" className="bg-[#0A0D14]">Exception Buy - Bullish Momentum</option>
                      <option value="hold" className="bg-[#0A0D14]">Exception Hold - Strategic Patience</option>
                      <option value="sell" className="bg-[#0A0D14]">Exit Protocol - Bearish Reversal</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest px-1">Source Payload (PDF)</label>
                    <div className="relative">
                      <input type="file" accept=".pdf" onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)} required className="w-full opacity-0 absolute inset-0 z-10 cursor-pointer" />
                      <div className="w-full bg-white/[0.01] border-2 border-dashed border-white/5 rounded-[2rem] py-12 flex flex-col items-center justify-center gap-4 transition-all hover:bg-white/[0.03] hover:border-cyan-500/20">
                        <Upload size={32} className="text-slate-700" />
                        <span className="text-xs font-black uppercase tracking-widest">{selectedFile ? selectedFile.name : 'Drop Analytical Memo'}</span>
                      </div>
                    </div>
                  </div>
                  {uploadStatus.msg && <div className={`p-4 rounded-2xl text-[11px] font-black tracking-wide border ${uploadStatus.type === 'success' ? 'bg-cyan-500/5 border-cyan-500/20 text-cyan-400' : 'bg-red-500/5 border-red-500/20 text-red-400'}`}>{uploadStatus.msg}</div>}
                  <button type="submit" className="w-full py-5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-2xl text-xs font-black uppercase tracking-[0.3em] transition-all shadow-2xl shadow-cyan-900/20 active:scale-95 cursor-pointer">Initiate Vectorization</button>
                </form>
              </div>

              <div className="bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-10">
                <h3 className="text-xl font-black text-white tracking-tight uppercase">Worker Grid</h3>
                <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2 scrollbar-hide">
                  {documents.map((doc) => (
                    <div key={doc.id} className="p-6 bg-white/[0.01] border border-white/5 rounded-[1.5rem] flex items-center justify-between gap-4">
                      <div className="space-y-1 min-w-0 flex-1">
                        <h4 className="text-xs font-black text-white truncate uppercase tracking-tight">{doc.company}</h4>
                        <span className="text-[8px] text-slate-600 font-black uppercase tracking-widest">{doc.sector} / {doc.recommendation}</span>
                      </div>
                      <div className={`px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest border ${doc.status === 'processed' ? 'bg-cyan-500/5 text-cyan-400 border-cyan-500/20' : 'bg-amber-500/5 text-amber-400 border-amber-500/20'}`}>
                        {doc.status === 'processed' ? 'Indexed' : 'Pending'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'Institutional Memory' && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
              <div className="bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-12 space-y-10 relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-1/2 h-full bg-cyan-500/5 blur-[120px] -z-10 group-hover:bg-cyan-500/10 transition-colors" />
                <div>
                  <h3 className="text-3xl font-black text-white tracking-tighter uppercase">Query Neural Store</h3>
                  <p className="text-[10px] text-slate-500 font-black tracking-[0.4em] uppercase mt-2">Semantic Cross-Referencing</p>
                </div>
                <form onSubmit={handleSemanticSearch} className="flex gap-4">
                  <div className="relative flex-1">
                    <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-cyan-400/50" size={20} />
                    <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Query rationale for asset allocation..." className="w-full bg-white/[0.02] border border-white/10 rounded-2xl pl-14 pr-6 py-5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 transition-all font-medium" />
                  </div>
                  <button type="submit" disabled={isSearching} className="px-10 py-5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-2xl text-[11px] font-black uppercase tracking-widest transition-all shadow-xl shadow-cyan-900/10 cursor-pointer disabled:opacity-50">
                    {isSearching ? 'Accessing Neural...' : 'Execute Semantic Query'}
                  </button>
                </form>
              </div>

              <div className="space-y-6">
                <span className="text-[10px] font-black text-slate-600 uppercase tracking-[0.4em] block px-2">Retrieved Passages ({searchResults.length})</span>
                {searchResults.length === 0 ? (
                  <div className="py-32 border-2 border-dashed border-white/5 rounded-[3rem] flex flex-col items-center justify-center text-slate-700 bg-white/[0.01]">
                    <Database size={48} className="opacity-20 mb-4" />
                    <span className="text-xs font-black uppercase tracking-widest opacity-40">Store Offline</span>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-6">
                    {searchResults.map((res, i) => (
                      <div key={i} className="p-10 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] space-y-6 group hover:border-cyan-500/20 transition-all">
                        <div className="flex justify-between items-center">
                          <h4 className="text-sm font-black text-cyan-400 uppercase tracking-tight flex items-center gap-3">
                            <FileText size={16} /> {res.company} / {res.sector}
                          </h4>
                          <span className="text-[10px] font-black font-mono text-slate-600 uppercase tracking-tighter">Match Prob: {(res.similarity * 100).toFixed(2)}% | Sector Access Node {res.page}</span>
                        </div>
                        <p className="text-sm text-slate-400 leading-relaxed font-medium p-8 bg-white/[0.01] border border-white/5 rounded-[2rem] relative group-hover:text-slate-300 transition-colors">
                          <span className="absolute top-0 left-0 w-1 h-full bg-cyan-500/20" />
                          "{res.content}"
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {activeTab === 'Earnings' && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 space-y-8">
                <div>
                  <h3 className="text-sm font-black text-cyan-400 uppercase tracking-widest flex items-center gap-2">
                    <Volume2 size={16} />
                    Live Audio Ingestion
                  </h3>
                  <p className="text-[10px] text-slate-500 mt-2 font-black uppercase tracking-widest">Earnings and Fed call monitor</p>
                </div>
                <div className="aspect-video bg-black/30 rounded-[2rem] flex flex-col items-center justify-center p-8 text-center border border-white/5 relative overflow-hidden group">
                  <div className="absolute inset-0 flex items-center justify-center opacity-20 group-hover:opacity-40 transition-opacity">
                    <div className="flex gap-1 h-24 items-end">
                      {Array.from({ length: 12 }).map((_, i) => (
                        <motion.div
                          key={i}
                          animate={{ height: [10, 40, 16, 72, 24] }}
                          transition={{ repeat: Infinity, duration: 1, delay: i * 0.1 }}
                          className="w-2 bg-cyan-400 rounded-t"
                        />
                      ))}
                    </div>
                  </div>
                  <div className="z-10 space-y-4">
                    <div className="w-16 h-16 rounded-full bg-cyan-500/20 flex items-center justify-center mx-auto ring-4 ring-cyan-500/10">
                      <Mic2 size={32} className="text-cyan-400" />
                    </div>
                    <div>
                      <h4 className="font-black text-white uppercase tracking-tight">Fed Press Briefing</h4>
                      <p className="text-[10px] text-slate-500 uppercase font-black tracking-widest">Speaker: Jerome Powell</p>
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-center gap-4">
                  <button
                    type="button"
                    onClick={() => setAudioPlaying(true)}
                    disabled={audioPlaying}
                    className="h-11 w-11 rounded-full border border-white/10 bg-white/[0.03] hover:bg-white/[0.07] disabled:opacity-50 flex items-center justify-center text-slate-300"
                    title="Start audio feed"
                  >
                    <Play size={16} className="fill-current" />
                  </button>
                  <button
                    type="button"
                    onClick={handleStopAudio}
                    disabled={!audioPlaying && !transcribing}
                    className="h-11 w-11 rounded-full border border-white/10 bg-white/[0.03] hover:bg-white/[0.07] disabled:opacity-50 flex items-center justify-center text-slate-300"
                    title="Stop audio feed"
                  >
                    <Square size={15} className="fill-current" />
                  </button>
                  <button
                    type="button"
                    onClick={handleTranscribe}
                    disabled={transcribing}
                    className="px-8 py-3 rounded-2xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-[10px] font-black uppercase tracking-widest flex items-center gap-2"
                  >
                    {transcribing ? <Loader2 size={15} className="animate-spin" /> : <FastForward size={15} />}
                    Transcribe
                  </button>
                </div>
              </div>

              <div className="lg:col-span-2 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] p-10 min-h-[520px] space-y-8">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-black text-cyan-400 uppercase tracking-widest flex items-center gap-2">
                    <Cpu size={16} />
                    ASR Transcription Feed
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${audioPlaying || transcribing ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
                    <span className={`text-[10px] font-black uppercase tracking-widest ${audioPlaying || transcribing ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {transcribing ? 'Transcribing' : audioPlaying ? 'Live' : 'Standby'}
                    </span>
                  </div>
                </div>
                {transcript ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4 font-mono text-sm leading-relaxed">
                    <p className="p-5 rounded-2xl bg-white/[0.03] border border-white/5 text-slate-300">
                      <span className="text-emerald-400 font-black">[00:00:12] JP:</span> Our primary objective remains stable prices and full employment. Recent data suggests cooling, but consumer spending is persistent.
                    </p>
                    <p className="p-5 rounded-2xl bg-white/[0.03] border border-white/5 text-slate-300">
                      <span className="text-emerald-400 font-black">[00:01:45] CFO:</span> {transcript}
                    </p>
                  </motion.div>
                ) : (
                  <div className="min-h-[360px] flex flex-col items-center justify-center text-slate-600 space-y-4">
                    <Mic2 size={48} className="opacity-30" />
                    <p className="text-sm italic">Initiate transcription to view speech-to-text conversion.</p>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </div>
      </main>

      {/* Slide-out Drawer */}
      <ExplainabilityDrawer
        violation={selectedViolation}
        institutionId={currentInstitution?.id || null}
        onClose={() => setSelectedViolation(null)}
      />
    </div>
  );
}

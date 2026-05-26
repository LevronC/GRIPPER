import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
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
  UserPlus
} from 'lucide-react';
import { useStore } from '../store/useStore';
import type { Holding, Violation } from '../store/useStore';
import ExplainabilityDrawer from './ExplainabilityDrawer';

// Static metadata of sectors for mapping
const SECTORS = ['Technology', 'Financials', 'Consumer Cyclical', 'Energy', 'Healthcare', 'Communication Services', 'Other'];

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
    setInstitution,
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
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const searchLimit = 3;
  const [isSearching, setIsSearching] = useState(false);

  // Editable Holdings state (local copy for draft edits)
  const [holdingsDraft, setHoldingsDraft] = useState<Holding[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [newWeight, setNewWeight] = useState(5);
  const [newCostBasis, setNewCostBasis] = useState(100);

  // Auth local state
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authInstId, setAuthInstId] = useState('');
  const [authRole, setAuthRole] = useState('analyst');
  const [authGradYear, setAuthGradYear] = useState<number | ''>('');
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');

  // Sandbox simulation local state
  const [simulationActive, setSimulationActive] = useState(false);
  const [simulationTriggered, setSimulationTriggered] = useState(false);

  // Load initial institutions
  useEffect(() => {
    fetchInstitutions();
  }, []);

  // Update holdings draft when global holdings change
  useEffect(() => {
    setHoldingsDraft(holdings);
  }, [holdings]);

  // Set default auth institution once loaded
  useEffect(() => {
    if (institutions.length > 0 && !authInstId) {
      setAuthInstId(institutions[0].id);
    }
  }, [institutions]);

  // Poll document ingestion progress periodically if there are pending docs
  useEffect(() => {
    if (!token || !currentInstitution) return;
    
    // Initial fetch
    fetchDocuments(currentInstitution.id);

    const interval = setInterval(() => {
      fetchDocuments(currentInstitution.id);
    }, 4000);

    return () => clearInterval(interval);
  }, [token, currentInstitution]);

  // Handle Auth submission
  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');

    if (!authInstId) {
      setAuthError('Please select an institution context.');
      return;
    }

    if (authMode === 'login') {
      const ok = await login(authEmail, authPassword, authInstId);
      if (!ok) {
        setAuthError('Invalid credentials. Check your password or institution selection.');
      }
    } else {
      const res = await register(
        authEmail, 
        authPassword, 
        authInstId, 
        authRole, 
        authGradYear === '' ? undefined : authGradYear
      );
      if (res.success) {
        setAuthSuccess('Registration successful! Please log in.');
        setAuthMode('login');
        setAuthPassword('');
      } else {
        setAuthError(res.error || 'Registration failed. Make sure the email is unique.');
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
    } catch (err) {
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
    return 'bg-amber-500/10 text-amber-400 border-amber-500/25';
  };

  // AUTH SCREEN COMPONENT
  if (!token) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#070A13] font-sans text-slate-100 relative overflow-hidden">
        {/* Glowing background highlights */}
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-500/10 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/10 blur-[120px]" />

        <motion.div 
          initial={{ opacity: 0, y: 30 }} 
          animate={{ opacity: 1, y: 0 }} 
          transition={{ duration: 0.5 }}
          className="w-full max-w-md bg-[#0C101F]/80 backdrop-blur-xl border border-slate-800 p-8 rounded-3xl shadow-2xl shadow-blue-900/10 space-y-6 z-10"
        >
          {/* Logo and title */}
          <div className="text-center space-y-2">
            <div className="mx-auto w-12 h-12 bg-gradient-to-tr from-blue-600 to-indigo-600 text-white rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Cpu size={24} />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-slate-100 to-slate-300 bg-clip-text text-transparent">
              GRIPPER RISK TERMINAL
            </h2>
            <p className="text-xs text-slate-400 font-medium uppercase tracking-widest">
              Multi-Tenant Investment Compliance
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleAuthSubmit} className="space-y-4">
            {/* Institution dropdown */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Building size={12} className="text-slate-500" />
                Select Institution Tenant
              </label>
              {institutions.length > 0 ? (
                <select
                  value={authInstId}
                  onChange={(e) => setAuthInstId(e.target.value)}
                  className="w-full bg-slate-900/80 border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
                >
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name} ({inst.slug.toUpperCase()})
                    </option>
                  ))}
                </select>
              ) : (
                <div className="h-9 animate-pulse bg-slate-800 rounded-xl"></div>
              )}
            </div>

            {/* Email input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Mail size={12} className="text-slate-500" />
                Corporate Email
              </label>
              <input
                type="email"
                required
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                placeholder="analyst@stetson.edu"
                className="w-full bg-slate-900/80 border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 placeholder-slate-650 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
              />
            </div>

            {/* Password input */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <Lock size={12} className="text-slate-500" />
                Security Password
              </label>
              <input
                type="password"
                required
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full bg-slate-900/80 border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 placeholder-slate-650 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
              />
            </div>

            {/* Registration specific fields */}
            {authMode === 'register' && (
              <motion.div 
                initial={{ opacity: 0, height: 0 }} 
                animate={{ opacity: 1, height: 'auto' }} 
                className="space-y-4 pt-1"
              >
                {/* Role select */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <UserPlus size={12} className="text-slate-500" />
                    Analyst Role
                  </label>
                  <select
                    value={authRole}
                    onChange={(e) => setAuthRole(e.target.value)}
                    className="w-full bg-slate-900/80 border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
                  >
                    <option value="analyst">Research Analyst</option>
                    <option value="sector_lead">Sector Lead</option>
                    <option value="pm">Portfolio Manager (PM)</option>
                    <option value="admin">Systems Administrator</option>
                  </select>
                </div>

                {/* Graduation Year */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                    Graduation Cohort Year (Optional)
                  </label>
                  <input
                    type="number"
                    value={authGradYear}
                    onChange={(e) => setAuthGradYear(e.target.value === '' ? '' : parseInt(e.target.value))}
                    placeholder="2027"
                    className="w-full bg-slate-900/80 border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 placeholder-slate-650 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all"
                  />
                </div>
              </motion.div>
            )}

            {/* Error Banner */}
            {authError && (
              <div className="p-3 bg-red-950/20 border border-red-900/40 text-red-400 rounded-xl text-xs">
                {authError}
              </div>
            )}

            {/* Success Banner */}
            {authSuccess && (
              <div className="p-3 bg-emerald-950/20 border border-emerald-800/40 text-emerald-400 rounded-xl text-xs">
                {authSuccess}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white rounded-xl text-xs font-bold transition shadow shadow-blue-500/10 cursor-pointer flex items-center justify-center gap-1.5"
            >
              {isLoading ? (
                <span>Verifying credentials...</span>
              ) : authMode === 'login' ? (
                <>Sign In to Workspace</>
              ) : (
                <>Register Analyst Account</>
              )}
            </button>
          </form>

          {/* Switcher */}
          <div className="text-center pt-2">
            <button
              type="button"
              onClick={() => {
                setAuthMode(authMode === 'login' ? 'register' : 'login');
                setAuthError('');
                setAuthSuccess('');
              }}
              className="text-xs text-slate-400 hover:text-slate-200 underline font-medium transition-colors"
            >
              {authMode === 'login' 
                ? "Don't have an account? Register here" 
                : 'Already registered? Log in here'}
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  // MAIN DASHBOARD LAYOUT
  return (
    <div className="flex h-screen bg-[#080B13] font-sans text-slate-100 overflow-hidden">
      {/* Sidebar Switcher & Navigation */}
      <aside className="w-72 bg-[#0C101F] border-r border-slate-800 p-6 flex flex-col z-10 select-none">
        
        {/* Title */}
        <div className="text-xl font-bold tracking-wider mb-6 flex items-center gap-2">
          <div className="bg-gradient-to-tr from-blue-600 to-indigo-600 text-white p-2 rounded-xl shadow-lg shadow-blue-500/10">
            <Cpu size={20} className="text-white" />
          </div>
          <span className="bg-gradient-to-r from-slate-100 to-slate-300 bg-clip-text text-transparent">GRIPPER</span>
          <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full font-mono font-bold tracking-tight">v1.2</span>
        </div>

        {/* Institutional Tenant Switcher */}
        <div className="mb-8 bg-slate-900/50 p-3 rounded-xl border border-slate-800 space-y-2">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <Building size={12} className="text-slate-500" />
            Institutional Context
          </span>
          {institutions.length > 0 ? (
            <select
              value={currentInstitution?.id || ''}
              onChange={(e) => {
                const selected = institutions.find(inst => inst.id === e.target.value);
                if (selected) setInstitution(selected);
              }}
              className="w-full bg-[#0F172A] border border-slate-800 rounded-lg py-1.5 px-2 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {institutions.map(inst => (
                <option key={inst.id} value={inst.id}>
                  {inst.name}
                </option>
              ))}
            </select>
          ) : (
            <div className="h-7 animate-pulse bg-slate-800 rounded-lg"></div>
          )}

          {currentPortfolio && (
            <div className="pt-2 border-t border-slate-850 flex justify-between items-center text-[10px]">
              <span className="text-slate-500">Active Fund:</span>
              <span className="font-mono text-slate-300 font-bold truncate max-w-[120px]">{currentPortfolio.name}</span>
            </div>
          )}
        </div>

        {/* Nav Tabs */}
        <nav className="flex-1 space-y-1.5">
          {[
            { id: 'Dashboard', label: 'Governance Center', icon: LayoutDashboard },
            { id: 'Portfolio', label: 'Portfolio & Exposures', icon: Scale },
            { id: 'SEC Ingestion', label: 'SEC Ingestion Hub', icon: Upload },
            { id: 'Institutional Memory', label: 'Institutional Memory', icon: Search }
          ].map((item) => {
            const isActive = activeTab === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl font-medium text-sm transition-all duration-200 border ${
                  isActive 
                    ? 'bg-blue-600/10 text-blue-400 border-blue-500/20 shadow-lg shadow-blue-500/5' 
                    : 'text-slate-400 border-transparent hover:bg-slate-900/50 hover:text-slate-200'
                }`}
              >
                <Icon size={16} className={isActive ? 'text-blue-400' : 'text-slate-500'} />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Footer Analyst Bio & Log Out */}
        <div className="mt-auto pt-6 border-t border-slate-850 flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-9 w-9 shrink-0 rounded-full bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center font-bold text-sm text-white shadow-md">
              {currentUser?.email.slice(0, 2).toUpperCase() || 'AN'}
            </div>
            <div className="truncate">
              <h5 className="text-xs font-bold text-slate-200 truncate">{currentUser?.email}</h5>
              <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider truncate">
                Role: {currentUser?.role}
              </p>
            </div>
          </div>
          <button 
            onClick={logout}
            title="Log Out"
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 hover:border-slate-700 transition"
          >
            <LogOut size={14} />
          </button>
        </div>
      </aside>

      {/* Main Terminal Viewport */}
      <main className="flex-1 overflow-y-auto p-8 relative flex flex-col bg-[#070A13]">
        
        {/* Top Header Controls */}
        <header className="flex justify-between items-center mb-8 border-b border-slate-850 pb-5">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">{activeTab}</h1>
            <p className="text-xs text-slate-500 mt-1 font-semibold uppercase tracking-wider">
              {currentInstitution?.name} &bull; {currentPortfolio?.name} ({currentPortfolio?.strategy_type} Strategy)
            </p>
          </div>

          <div className="flex gap-3">
            {currentPortfolio && (
              <button
                onClick={() => evaluateCompliance(currentPortfolio.id, currentInstitution!.id)}
                disabled={isLoading}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs font-bold tracking-wide transition-colors flex items-center gap-2 cursor-pointer shadow-md disabled:opacity-50"
              >
                <Database size={13} className="text-blue-400" />
                Run Compliance Check
              </button>
            )}
          </div>
        </header>

        {/* Viewport Content */}
        <div className="flex-1 max-w-6xl w-full mx-auto space-y-8">
          
          {/* TAB 1: GOVERNANCE CENTER */}
          {activeTab === 'Dashboard' && (
            <motion.div 
              initial={{ opacity: 0, y: 15 }} 
              animate={{ opacity: 1, y: 0 }} 
              className="space-y-6"
            >
              {/* Summary Stats Grid */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-[#0C1020] border border-slate-800 p-5 rounded-2xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Compliance Score</span>
                  <div className="flex items-baseline gap-2 mt-2">
                    <span className="text-3xl font-black font-mono text-emerald-400">{complianceScore}%</span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full mt-3 overflow-hidden">
                    <div className="bg-emerald-400 h-full transition-all duration-500" style={{ width: `${complianceScore}%` }} />
                  </div>
                </div>

                <div className="bg-[#0C1020] border border-slate-800 p-5 rounded-2xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Active Violations</span>
                  <div className="flex items-baseline gap-2 mt-2">
                    <span className={`text-3xl font-black font-mono ${activeAlertsCount > 0 ? 'text-red-400' : 'text-slate-400'}`}>
                      {activeAlertsCount}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-2 font-medium">Requires RAG validation reports</p>
                </div>

                <div className="bg-[#0C1020] border border-slate-800 p-5 rounded-2xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Resolved Exceptions</span>
                  <div className="flex items-baseline gap-2 mt-2">
                    <span className="text-3xl font-black font-mono text-emerald-400">{resolvedViolations.length}</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-2 font-medium">Permanently archived in audit trail</p>
                </div>

                <div className="bg-[#0C1020] border border-slate-800 p-5 rounded-2xl">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Portfolio Assets</span>
                  <div className="flex items-baseline gap-2 mt-2">
                    <span className="text-3xl font-black font-mono text-slate-350">{holdings.length}</span>
                    <span className="text-xs text-slate-500 font-mono">/ {(totalHoldingsWeight * 100).toFixed(0)}% weight</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-2 font-medium">Aggregated across all tickers</p>
                </div>
              </div>

              {/* Main dashboard splits */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Active Alerts List */}
                <div className="lg:col-span-2 bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-4">
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <ShieldAlert size={16} className="text-red-400" />
                    Active IPS Governance Breaches
                  </h3>
                  
                  {violations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 border border-dashed border-slate-800 rounded-xl space-y-3 bg-slate-900/10">
                      <CheckCircle size={32} className="text-emerald-500" />
                      <p className="text-xs text-slate-400 font-bold tracking-wide">PORTFOLIO FULLY IPS COMPLIANT</p>
                      <p className="text-[10px] text-slate-500 max-w-[250px] text-center leading-relaxed">
                        No policy threshold deviations detected. All positions and weights conform with Stetson IPS regulations.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {violations.map((v) => (
                        <div key={v.id} className="p-4 bg-slate-900/40 border border-slate-850 hover:border-slate-800 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4 transition-all">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${getSeverityBadge(v.severity)}`}>
                                {v.severity}
                              </span>
                              <span className="text-xs font-mono font-bold text-slate-200 capitalize">
                                {v.event_type.replace(/_/g, ' ')}
                              </span>
                            </div>
                            <p className="text-xs text-slate-400 leading-relaxed max-w-md">
                              {v.details.message}
                            </p>
                          </div>
                          <button
                            onClick={() => setSelectedViolation(v)}
                            className="px-3.5 py-1.5 bg-blue-600/10 hover:bg-blue-600 border border-blue-500/20 hover:border-blue-500 rounded-lg text-[10px] font-bold tracking-wider text-blue-400 hover:text-white transition-all flex items-center gap-1.5 cursor-pointer shadow"
                          >
                            <Sparkles size={11} />
                            RAG Analysis
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Audit & Compliance Log */}
                <div className="bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-4">
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Clock size={16} className="text-blue-400" />
                    Board Audit Trail
                  </h3>

                  <div className="space-y-4 overflow-y-auto max-h-[350px] pr-2">
                    {/* Active Violations (Timeline Items) */}
                    {violations.map((v) => (
                      <div key={v.id} className="flex gap-3 text-xs">
                        <div className="flex flex-col items-center">
                          <div className="h-2 w-2 rounded-full bg-red-400 mt-1.5" />
                          <div className="w-[1px] bg-slate-850 flex-1 my-1" />
                        </div>
                        <div className="pb-4">
                          <span className="font-semibold text-slate-300">Violation Opened: {v.event_type.replace(/_/g, ' ')}</span>
                          <span className="block text-[10px] text-slate-500 mt-0.5">{new Date(v.created_at).toLocaleString()}</span>
                          <p className="text-[10px] text-slate-400 leading-relaxed mt-1">{v.details.message}</p>
                        </div>
                      </div>
                    ))}

                    {/* Resolved Violations (Timeline Items) */}
                    {resolvedViolations.map((v) => (
                      <div key={v.id} className="flex gap-3 text-xs">
                        <div className="flex flex-col items-center">
                          <div className="h-2 w-2 rounded-full bg-emerald-400 mt-1.5" />
                          <div className="w-[1px] bg-slate-850 flex-1 my-1" />
                        </div>
                        <div className="pb-4">
                          <span className="font-semibold text-emerald-400">Violation Resolved: {v.event_type.replace(/_/g, ' ')}</span>
                          <span className="block text-[10px] text-slate-500 mt-0.5">
                            Resolved at {v.resolved_at ? new Date(v.resolved_at).toLocaleString() : 'N/A'}
                          </span>
                          <p className="text-[10px] text-slate-400 leading-relaxed mt-1">{v.details.message}</p>
                        </div>
                      </div>
                    ))}

                    {violations.length === 0 && resolvedViolations.length === 0 && (
                      <div className="text-center py-8 text-[10px] text-slate-500 font-mono">
                        Audit trail empty.
                      </div>
                    )}
                  </div>
                </div>

              </div>
            </motion.div>
          )}

          {/* TAB 2: PORTFOLIO & RULES */}
          {activeTab === 'Portfolio' && (
            <motion.div 
              initial={{ opacity: 0, y: 15 }} 
              animate={{ opacity: 1, y: 0 }} 
              className="space-y-6"
            >
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Holdings Manager (Edit holdings weights) */}
                <div className="lg:col-span-2 bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-5">
                  <div className="flex justify-between items-center border-b border-slate-850 pb-4">
                    <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
                      Portfolio Weight Allocations
                    </h3>
                    <div className="text-xs text-slate-500 flex gap-4">
                      <span>
                        Total Allocated: <span className={`font-bold font-mono ${totalHoldingsWeight > 1.0 ? 'text-red-400' : 'text-slate-350'}`}>
                          {(totalHoldingsWeight * 100).toFixed(1)}%
                        </span>
                      </span>
                    </div>
                  </div>

                  {/* Add Holding Form Inline */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3 bg-slate-900/30 p-4 border border-slate-850 rounded-xl items-end">
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Ticker</label>
                      <input 
                        type="text" 
                        value={newTicker}
                        onChange={(e) => setNewTicker(e.target.value)}
                        placeholder="e.g. AAPL"
                        className="w-full bg-[#0F172A] border border-slate-800 rounded-lg py-1 px-2.5 text-xs text-slate-200 focus:outline-none"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Weight (%)</label>
                      <input 
                        type="number" 
                        value={newWeight}
                        onChange={(e) => setNewWeight(parseFloat(e.target.value) || 0)}
                        placeholder="5"
                        className="w-full bg-[#0F172A] border border-slate-800 rounded-lg py-1 px-2.5 text-xs text-slate-200 focus:outline-none"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Cost Basis ($)</label>
                      <input 
                        type="number" 
                        value={newCostBasis}
                        onChange={(e) => setNewCostBasis(parseFloat(e.target.value) || 0)}
                        placeholder="150"
                        className="w-full bg-[#0F172A] border border-slate-800 rounded-lg py-1 px-2.5 text-xs text-slate-200 focus:outline-none"
                      />
                    </div>
                    <button 
                      onClick={addDraftHolding}
                      className="w-full bg-blue-600 hover:bg-blue-500 py-1.5 px-3 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 cursor-pointer shadow-md"
                    >
                      <Plus size={14} /> Add Asset
                    </button>
                  </div>

                  {/* List of draft holdings */}
                  <div className="space-y-3.5 pt-2 max-h-[300px] overflow-y-auto pr-2">
                    {holdingsDraft.map((h, index) => (
                      <div key={index} className="p-3.5 bg-slate-900/20 border border-slate-850 rounded-xl flex items-center justify-between gap-4">
                        <div className="w-20">
                          <span className="text-xs font-black font-mono text-slate-200">{h.ticker}</span>
                        </div>

                        <div className="flex-1 flex items-center gap-3">
                          <input 
                            type="range" 
                            min="0" 
                            max="50" 
                            value={Math.round(h.weight * 100)} 
                            onChange={(e) => updateDraftWeight(index, parseInt(e.target.value))}
                            className="flex-1 accent-blue-500 h-1 rounded-lg bg-slate-800"
                          />
                          <span className="text-xs font-bold font-mono text-slate-400 w-10 text-right">
                            {Math.round(h.weight * 100)}%
                          </span>
                        </div>

                        <div className="w-24 text-right">
                          <span className="text-[10px] text-slate-500 block">Cost Basis</span>
                          <span className="text-xs font-mono font-medium text-slate-350">${h.cost_basis}</span>
                        </div>

                        <button 
                          onClick={() => removeDraftHolding(index)}
                          className="text-slate-600 hover:text-red-400 p-1 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Sandbox control & Commit buttons */}
                  <div className="border-t border-slate-850 pt-4 flex justify-between items-center">
                    <button
                      onClick={() => {
                        setSimulationActive(!simulationActive);
                        if (!simulationActive) {
                          setSimulationTriggered(false);
                        }
                      }}
                      className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
                        simulationActive 
                          ? 'bg-amber-600/10 text-amber-400 border border-amber-500/20' 
                          : 'bg-slate-900 border border-slate-800 text-slate-300'
                      }`}
                    >
                      <Sparkles size={13} />
                      {simulationActive ? 'Disable Sandbox' : 'Enable Simulation Sandbox'}
                    </button>

                    <button 
                      onClick={commitHoldings}
                      disabled={isLoading}
                      className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-800 text-white font-bold py-2.5 px-5 rounded-xl text-xs transition shadow shadow-emerald-500/10 cursor-pointer"
                    >
                      Save Portfolio Changes
                    </button>
                  </div>

                  {/* Sandbox results panel */}
                  {simulationActive && (
                    <motion.div 
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mt-4 p-5 bg-amber-950/10 border border-amber-900/30 rounded-2xl space-y-4"
                    >
                      <div className="flex justify-between items-center">
                        <div>
                          <h4 className="text-xs font-extrabold text-amber-400 uppercase tracking-widest flex items-center gap-1.5">
                            <Sparkles size={13} />
                            Scenario Simulation Sandbox
                          </h4>
                          <p className="text-[10px] text-slate-500 mt-0.5">
                            Evaluate rule violations hypothetically without modifying actual database holdings.
                          </p>
                        </div>

                        <button
                          onClick={handleSandboxSimulate}
                          disabled={isLoading}
                          className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-955 rounded-lg text-[10px] font-black tracking-wider transition uppercase"
                        >
                          {isLoading ? 'Running check...' : 'Run Simulation'}
                        </button>
                      </div>

                      {simulationTriggered && (
                        <div className="space-y-2">
                          <span className="text-[10px] font-bold text-slate-450 uppercase tracking-wider block">
                            Simulated Compliance Outputs ({simulatedViolations.length})
                          </span>
                          
                          {simulatedViolations.length === 0 ? (
                            <div className="flex items-center gap-2 p-3 bg-emerald-950/20 border border-emerald-900/40 text-emerald-450 rounded-xl text-xs">
                              <CheckCircle size={14} className="text-emerald-400" />
                              <span>Hypothetical portfolio remains fully compliant with active IPS regulations.</span>
                            </div>
                          ) : (
                            <div className="space-y-2 max-h-[160px] overflow-y-auto pr-1">
                              {simulatedViolations.map((v, i) => (
                                <div key={i} className="p-3 bg-red-950/10 border border-red-900/30 rounded-xl flex justify-between items-start text-xs gap-3">
                                  <div>
                                    <div className="flex items-center gap-1.5">
                                      <span className="h-1.5 w-1.5 rounded-full bg-red-450" />
                                      <span className="font-bold text-red-400 uppercase font-mono tracking-tight">{v.event_type}</span>
                                    </div>
                                    <p className="text-[10px] text-slate-400 mt-1">{v.details.message}</p>
                                  </div>
                                  <span className="text-[9px] bg-red-500/10 text-red-400 border border-red-500/20 px-2 py-0.5 rounded font-mono font-bold capitalize">
                                    {v.severity}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </motion.div>
                  )}
                </div>

                {/* SVG Sector exposure comparison chart */}
                <div className="bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-6">
                  <div>
                    <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
                      Sector Exposures vs. Limits
                    </h3>
                    <p className="text-[10px] text-slate-500 mt-1">Comparing total weights relative to 30% IPS limits</p>
                  </div>

                  {/* Built-in SVG exposure chart */}
                  <div className="space-y-4 pt-2">
                    {SECTORS.map((sec) => {
                      // Calculate weight for sector
                      const secWeight = holdings.reduce((sum, h) => {
                        // Quick lookup for sectors matching rules.py
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
                        <div key={sec} className="space-y-1.5">
                          <div className="flex justify-between text-[10px] font-semibold">
                            <span className="text-slate-400">{sec}</span>
                            <span className={isBreached ? 'text-red-400 font-bold' : 'text-slate-500'}>
                              {pct.toFixed(1)}% <span className="text-[8px] font-normal text-slate-600">/ 30.0%</span>
                            </span>
                          </div>
                          <div className="h-2 w-full bg-slate-900 rounded-full overflow-hidden relative border border-slate-850">
                            {/* Limit marker line */}
                            <div className="absolute top-0 bottom-0 left-[30%] w-[1px] bg-red-500/50 z-10 border-dashed" />
                            <div 
                              className={`h-full transition-all duration-300 ${isBreached ? 'bg-red-500' : 'bg-blue-500/80'}`}
                              style={{ width: `${Math.min(100, (pct / 100) * 100)}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

              </div>
            </motion.div>
          )}

          {/* TAB 3: SEC INGESTION HUB */}
          {activeTab === 'SEC Ingestion' && (
            <motion.div 
              initial={{ opacity: 0, y: 15 }} 
              animate={{ opacity: 1, y: 0 }} 
              className="grid grid-cols-1 lg:grid-cols-3 gap-6"
            >
              {/* Form panel */}
              <div className="lg:col-span-2 bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Upload size={16} className="text-blue-400" />
                    Gripper Ingestion Pipeline
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">Upload analyst memos or committee proposals for background processing.</p>
                </div>

                <form onSubmit={handleUpload} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Company name (Ticker)</label>
                      <input 
                        type="text" 
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        placeholder="e.g. Tesla (TSLA)"
                        required
                        className="w-full bg-[#0F172A] border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Sector Class</label>
                      <select 
                        value={sector}
                        onChange={(e) => setSector(e.target.value)}
                        className="w-full bg-[#0F172A] border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 focus:outline-none"
                      >
                        {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Recommendation</label>
                      <select 
                        value={recommendation}
                        onChange={(e) => setRecommendation(e.target.value)}
                        className="w-full bg-[#0F172A] border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 focus:outline-none"
                      >
                        <option value="buy">Exception Buy Recommendation</option>
                        <option value="hold">Hold Exception</option>
                        <option value="sell">Exit Thesis Rationale</option>
                      </select>
                    </div>
                    
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Select PDF Document</label>
                      <input 
                        type="file" 
                        accept=".pdf"
                        onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)}
                        required
                        className="w-full text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-[10px] file:font-bold file:uppercase file:bg-blue-600/10 file:text-blue-400 hover:file:bg-blue-600/20 file:cursor-pointer text-slate-400 bg-[#0F172A] border border-slate-800 rounded-xl py-1 px-3"
                      />
                    </div>
                  </div>

                  {uploadStatus.msg && (
                    <div className={`p-3 rounded-lg text-xs border ${
                      uploadStatus.type === 'success' ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-400' : 'bg-red-950/20 border-red-900/50 text-red-400'
                    }`}>
                      {uploadStatus.msg}
                    </div>
                  )}

                  <button 
                    type="submit"
                    className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-xs font-bold tracking-wider text-white shadow shadow-blue-500/15 cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    <Upload size={14} /> Ingest & Vectorize Document
                  </button>
                </form>
              </div>

              {/* Status queue list (Real backend documents + workers status) */}
              <div className="bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
                    RQ Background Workers
                  </h3>
                  <p className="text-[10px] text-slate-500 mt-1">Ingestion and vectorization pipeline status</p>
                </div>

                <div className="space-y-3.5 max-h-[350px] overflow-y-auto pr-1">
                  {documents.map((doc) => (
                    <div key={doc.id} className="p-3.5 bg-slate-900/40 border border-slate-850 rounded-xl flex items-center justify-between gap-3">
                      <div className="space-y-1 min-w-0 flex-1">
                        <span className="text-xs font-bold text-slate-350 truncate block">{doc.company}</span>
                        <span className="text-[9px] text-slate-500 font-medium uppercase font-mono block">
                          {doc.sector} &bull; Rec: {doc.recommendation}
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        {doc.status === 'pending' || doc.status === 'processing' ? (
                          <div className="flex items-center gap-1.5 bg-blue-500/10 border border-blue-500/25 px-2 py-0.5 rounded">
                            <span className="h-1 w-1 rounded-full bg-blue-400 animate-ping" />
                            <span className="text-[9px] font-bold text-blue-400 uppercase tracking-wider">Vectorizing</span>
                          </div>
                        ) : doc.status === 'failed' ? (
                          <div className="flex items-center gap-1.5 bg-red-500/10 border border-red-500/25 px-2 py-0.5 rounded">
                            <span className="h-1 w-1 rounded-full bg-red-400" />
                            <span className="text-[9px] font-bold text-red-400 uppercase tracking-wider">Failed</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 rounded">
                            <span className="h-1 w-1 rounded-full bg-emerald-400" />
                            <span className="text-[9px] font-bold text-emerald-400 uppercase tracking-wider">Indexed</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}

                  {documents.length === 0 && (
                    <div className="text-center py-12 text-[10px] text-slate-500 font-mono border border-slate-850 border-dashed rounded-xl">
                      No reports uploaded or processed for this tenant context yet.
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}

          {/* TAB 4: INSTITUTIONAL MEMORY */}
          {activeTab === 'Institutional Memory' && (
            <motion.div 
              initial={{ opacity: 0, y: 15 }} 
              animate={{ opacity: 1, y: 0 }} 
              className="space-y-6"
            >
              {/* Search form */}
              <div className="bg-[#0C1020] border border-slate-800 rounded-2xl p-6 space-y-5">
                <div>
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
                    Semantic Search Interface
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Directly query the RLS-isolated BGE vector store database.
                  </p>
                </div>

                <form onSubmit={handleSemanticSearch} className="flex gap-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                    <input 
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="e.g. exception rationale for TSLA buy..."
                      className="w-full bg-[#0F172A] border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-xs text-slate-200 focus:outline-none"
                    />
                  </div>
                  <button 
                    type="submit"
                    disabled={isSearching}
                    className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white rounded-xl text-xs font-bold transition shadow shadow-blue-500/10 cursor-pointer flex items-center gap-2"
                  >
                    {isSearching ? 'Querying...' : 'Semantic Search'}
                  </button>
                </form>
              </div>

              {/* Search results */}
              <div className="space-y-4">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block">
                  Vector Matching Passages ({searchResults.length})
                </span>

                {searchResults.length === 0 ? (
                  <div className="text-center py-16 border border-slate-800 border-dashed rounded-2xl text-xs text-slate-500">
                    {searchQuery ? 'No matching passages retrieved.' : 'Enter a query to search vector database.'}
                  </div>
                ) : (
                  <div className="space-y-4">
                    {searchResults.map((res, i) => (
                      <div key={i} className="p-5 bg-[#0C1020] border border-slate-800 rounded-2xl space-y-3">
                        <div className="flex justify-between items-center text-xs">
                          <span className="font-bold text-blue-400 flex items-center gap-1">
                            <FileText size={13} />
                            {res.company} ({res.sector})
                          </span>
                          <span className="bg-slate-900 border border-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
                            Cosine Similarity: {(res.similarity * 100).toFixed(1)}% | Page {res.page}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 leading-relaxed font-mono p-3 bg-slate-950/50 border border-slate-850 rounded-xl">
                          {res.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}

        </div>
      </main>

      {/* Slide-out Explainability Drawer */}
      <ExplainabilityDrawer
        violation={selectedViolation}
        institutionId={currentInstitution?.id || null}
        onClose={() => setSelectedViolation(null)}
      />
    </div>
  );
}

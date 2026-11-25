import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { 
  ShieldAlert, 
  FileText, 
  Scale, 
  Search, 
  Plus, 
  Trash2, 
  Database,
  Upload,
  Clock,
  LogOut,
  ShieldCheck,
  Fingerprint,
  Zap,
  Activity,
  History
} from 'lucide-react';
import { useStore } from '../store/useStore';
import type { Holding, Violation } from '../store/useStore';
import ExplainabilityDrawer from './ExplainabilityDrawer';
import { apiUrl } from '../lib/api';
import AuthPanel from './AuthPanel';

// Static metadata of sectors for mapping
const SECTORS = ['Technology', 'Financials', 'Consumer Cyclical', 'Energy', 'Healthcare', 'Communication Services', 'Other'];


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
  const [searchDegraded, setSearchDegraded] = useState<string | null>(null);

  // Editable Holdings state (local copy for draft edits)
  const [holdingsDraft, setHoldingsDraft] = useState<Holding[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [newWeight, setNewWeight] = useState(5);
  const [newCostBasis, setNewCostBasis] = useState(100);

  // Sandbox simulation local state
  const [simulationActive, setSimulationActive] = useState(false);
  const [simulationTriggered, setSimulationTriggered] = useState(false);

  // Load the signed-in user's institution
  useEffect(() => {
    if (token) fetchInstitutions();
  }, [token, fetchInstitutions]);

  // Update holdings draft when global holdings change
  useEffect(() => {
    // The matrix is an editable draft; reset it when backend holdings change.
    setHoldingsDraft(holdings);
  }, [holdings]);

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
      const res = await fetch(apiUrl('/documents/upload'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token || ''}`
        },
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        if (data.status === 'failed') {
          setUploadStatus({ type: 'error', msg: data.message || 'Ingestion failed. You can retry it from the document list.' });
        } else if (data.status === 'pending') {
          setUploadStatus({ type: 'success', msg: 'Document uploaded and queued for ingestion.' });
        } else {
          setUploadStatus({ type: 'success', msg: data.status === 'duplicate' ? 'This document was already ingested.' : 'Document uploaded and indexed.' });
        }
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
      const res = await fetch(apiUrl('/search/semantic'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
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
        setSearchDegraded(
          data.retrieval_mode === 'full_text_only'
            ? 'Semantic search is unavailable, so results come from keyword (full-text) matching only.'
            : null,
        );
      } else {
        console.error('Search failed');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  };

  const handleRetryDocument = async (reportId: string) => {
    if (!currentInstitution) return;
    try {
      await fetch(apiUrl(`/documents/${reportId}/retry`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token || ''}` },
      });
    } finally {
      fetchDocuments(currentInstitution.id);
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

  // Render helpers
  const getSeverityBadge = (sev: string) => {
    if (sev === 'critical') {
      return 'bg-red-500/10 text-red-400 border-red-500/25';
    }
    return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/25';
  };

  // AUTH SCREEN COMPONENT
  if (!token) {
    return <AuthPanel />;
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
            { id: 'Portfolio', label: 'Portfolio Matrix', icon: Scale },
            { id: 'SEC Ingestion', label: 'Ingestion Pipeline', icon: Upload },
            { id: 'Institutional Memory', label: 'Research Search', icon: Search }
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
                  { label: 'Open violations', value: activeAlertsCount, pct: Math.min(100, activeAlertsCount * 10), color: activeAlertsCount > 0 ? 'text-red-400' : 'text-slate-400', bg: 'bg-red-500' },
                  { label: 'Resolved violations', value: resolvedViolations.length, pct: Math.min(100, resolvedViolations.length * 10), color: 'text-emerald-400', bg: 'bg-emerald-500' },
                  { label: 'Holdings', value: holdings.length, pct: Math.min(100, holdings.length * 5), color: 'text-white', bg: 'bg-cyan-500' },
                  { label: 'Allocated weight', value: `${(totalHoldingsWeight * 100).toFixed(1)}%`, pct: Math.min(100, totalHoldingsWeight * 100), color: 'text-white', bg: 'bg-blue-500' }
                ].map((stat, i) => (
                  <div key={i} className="bg-[#0A0D14] border border-white/5 p-8 rounded-[2rem] space-y-4">
                    <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest block">{stat.label}</span>
                    <div className="text-4xl font-black tracking-tighter transition-colors font-mono">{stat.value}</div>
                    <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
                      <div className={`${stat.bg} h-full transition-all duration-700`} style={{ width: `${stat.pct}%` }} />
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
                            <FileText size={12} />
                            Explain
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
                        {doc.error_message && (doc.status === 'failed' || doc.status === 'duplicate') && (
                          <p className="text-[10px] text-slate-500 leading-snug">{doc.error_message}</p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <div className={`px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest border ${
                          doc.status === 'processed' ? 'bg-cyan-500/5 text-cyan-400 border-cyan-500/20'
                            : doc.status === 'failed' ? 'bg-red-500/5 text-red-400 border-red-500/20'
                              : 'bg-amber-500/5 text-amber-400 border-amber-500/20'}`}>
                          {doc.status === 'processed' && doc.index_mode === 'keyword_only'
                            ? 'Indexed (keyword only)'
                            : ({ processed: 'Indexed', pending: 'Pending', processing: 'Processing', failed: 'Failed', duplicate: 'Duplicate' } as Record<string, string>)[doc.status] ?? doc.status}
                        </div>
                        {doc.status === 'failed' && (
                          <button type="button" onClick={() => handleRetryDocument(doc.id)}
                            className="text-[9px] font-black uppercase tracking-widest text-slate-400 hover:text-cyan-400">
                            Retry
                          </button>
                        )}
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
                  <h3 className="text-3xl font-black text-white tracking-tighter uppercase">Search research</h3>
                  <p className="text-[10px] text-slate-500 font-black tracking-[0.4em] uppercase mt-2">Semantic Cross-Referencing</p>
                </div>
                <form onSubmit={handleSemanticSearch} className="flex gap-4">
                  <div className="relative flex-1">
                    <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-cyan-400/50" size={20} />
                    <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Query rationale for asset allocation..." className="w-full bg-white/[0.02] border border-white/10 rounded-2xl pl-14 pr-6 py-5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 transition-all font-medium" />
                  </div>
                  <button type="submit" disabled={isSearching} className="px-10 py-5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-2xl text-[11px] font-black uppercase tracking-widest transition-all shadow-xl shadow-cyan-900/10 cursor-pointer disabled:opacity-50">
                    {isSearching ? 'Searching...' : 'Search'}
                  </button>
                </form>
              </div>

              <div className="space-y-6">
                {searchDegraded && (
                  <div role="status" className="p-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 text-amber-300 text-xs font-medium">
                    {searchDegraded}
                  </div>
                )}
                <span className="text-[10px] font-black text-slate-600 uppercase tracking-[0.4em] block px-2">Retrieved Passages ({searchResults.length})</span>
                {searchResults.length === 0 ? (
                  <div className="py-32 border-2 border-dashed border-white/5 rounded-[3rem] flex flex-col items-center justify-center text-slate-700 bg-white/[0.01]">
                    <Database size={48} className="opacity-20 mb-4" />
                    <span className="text-xs font-black uppercase tracking-widest opacity-40">No results</span>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-6">
                    {searchResults.map((res, i) => (
                      <div key={i} className="p-10 bg-[#0A0D14] border border-white/5 rounded-[2.5rem] space-y-6 group hover:border-cyan-500/20 transition-all">
                        <div className="flex justify-between items-center">
                          <h4 className="text-sm font-black text-cyan-400 uppercase tracking-tight flex items-center gap-3">
                            <FileText size={16} /> {res.company} / {res.sector}
                          </h4>
                          <span className="text-[10px] font-black font-mono text-slate-600 uppercase tracking-tighter">{res.page != null ? `Page ${res.page}` : 'Page n/a'}</span>
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

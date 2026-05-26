import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ShieldAlert, Sparkles, FileText, Bookmark, Info } from 'lucide-react';
import { useStore } from '../store/useStore';
import type { Violation } from '../store/useStore';

interface Evidence {
  report_id: string;
  page: number;
  content: string;
  similarity: number;
  sector: string;
  company: string;
}

interface ExplanationResult {
  message: string;
  compliance_status: string;
  ai_explanation_draft: string;
  evidence: Evidence[];
}

interface ExplainabilityDrawerProps {
  violation: Violation | null;
  institutionId: string | null;
  onClose: () => void;
}

export default function ExplainabilityDrawer({ violation, institutionId, onClose }: ExplainabilityDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExplanationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const token = useStore((state) => state.token);

  useEffect(() => {
    if (!violation || !institutionId) {
      return;
    }

    const fetchExplanation = async () => {
      setLoading(true);
      setError(null);
      setResult(null);
      try {
        const res = await fetch(`http://localhost:8000/violations/${violation.id}/explain`, {
          method: 'POST',
          headers: {
            'X-Institution-ID': institutionId,
            'Authorization': `Bearer ${token || ''}`
          }
        });
        if (res.ok) {
          const data = await res.json();
          setResult(data);
        } else {
          const errData = await res.json();
          setError(errData.detail || 'Failed to retrieve exception justification.');
        }
      } catch (err) {
        setError('Network error trying to fetch RAG exception data.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchExplanation();
  }, [violation, institutionId, token]);

  return (
    <AnimatePresence>
      {violation && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.4 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black z-40"
          />

          {/* Drawer Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed inset-y-0 right-0 w-full max-w-2xl bg-slate-900 text-slate-100 shadow-2xl z-50 flex flex-col border-l border-slate-800"
          >
            {/* Header */}
            <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-slate-950">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-xl ${
                  violation.severity === 'critical' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'
                }`}>
                  <ShieldAlert size={20} />
                </div>
                <div>
                  <h3 className="font-bold text-lg tracking-tight">Compliance Justification</h3>
                  <p className="text-xs text-slate-400 font-medium">Audit RAG Precedent Explorer</p>
                </div>
              </div>
              <button 
                onClick={onClose}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Breach Details Card */}
              <div className="p-5 bg-slate-950 border border-slate-800 rounded-2xl space-y-4">
                <div className="flex justify-between items-start">
                  <div>
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Violation Type</span>
                    <h4 className="font-bold text-slate-200 mt-1 capitalize">
                      {violation.event_type.replace(/_/g, ' ')}
                    </h4>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold border capitalize ${
                    violation.severity === 'critical' 
                      ? 'bg-red-500/10 text-red-400 border-red-500/20' 
                      : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  }`}>
                    {violation.severity}
                  </span>
                </div>

                <p className="text-sm text-slate-300 leading-relaxed bg-slate-900/50 p-3 rounded-xl border border-slate-800/50">
                  {violation.details.message}
                </p>

                {/* Progress Bar comparison */}
                {violation.details.current_weight !== undefined && violation.details.threshold !== undefined && (
                  <div className="space-y-1.5 pt-2">
                    <div className="flex justify-between text-xs font-semibold">
                      <span className="text-slate-400">IPS Threshold: {(violation.details.threshold * 100).toFixed(1)}%</span>
                      <span className="text-red-400">Current Weight: {(violation.details.current_weight * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex">
                      <div 
                        className="bg-slate-600 h-full" 
                        style={{ width: `${Math.min(100, (violation.details.threshold / violation.details.current_weight) * 100)}%` }}
                      />
                      <div 
                        className="bg-red-500 h-full flex-1"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* RAG Content Loading / Error / Display */}
              <div className="space-y-4">
                <h4 className="font-semibold text-slate-300 flex items-center gap-2 text-sm uppercase tracking-wider">
                  <Sparkles size={16} className="text-blue-400" />
                  RAG Retrieval Report
                </h4>

                {loading && (
                  <div className="space-y-4 animate-pulse">
                    <div className="h-10 bg-slate-850 rounded-xl"></div>
                    <div className="h-28 bg-slate-850 rounded-xl"></div>
                    <div className="h-32 bg-slate-850 rounded-xl"></div>
                  </div>
                )}

                {error && (
                  <div className="p-4 bg-red-950/20 border border-red-900/50 text-red-300 rounded-xl text-sm flex gap-3">
                    <Info size={16} className="shrink-0 mt-0.5" />
                    <p>{error}</p>
                  </div>
                )}

                {!loading && !error && result && (
                  <div className="space-y-6">
                    {/* Status Banner */}
                    <div className={`p-4 rounded-xl border text-sm flex gap-3 ${
                      result.compliance_status === 'retrieval_justified'
                        ? 'bg-emerald-950/30 border-emerald-800/40 text-emerald-300'
                        : 'bg-slate-850 border-slate-850 text-slate-300'
                    }`}>
                      <Bookmark size={18} className="shrink-0 mt-0.5" />
                      <div>
                        <div className="font-bold capitalize">
                          {result.compliance_status === 'retrieval_justified' 
                            ? 'Approved Exception Precedent Found' 
                            : 'No IPS Exception Documented'}
                        </div>
                        <p className="text-xs text-slate-400 mt-1">
                          {result.compliance_status === 'retrieval_justified'
                            ? 'A qualitative investment committee exception has been semantically matched to this position.'
                            : 'No recent board reports or analyst buy proposals explain this overweight allocation.'}
                        </p>
                      </div>
                    </div>

                    {/* AI Draft Rationale */}
                    <div className="p-5 bg-gradient-to-r from-blue-950/20 to-slate-900 border border-blue-900/30 rounded-2xl space-y-3">
                      <div className="flex items-center gap-1.5 text-xs font-bold text-blue-400 uppercase tracking-wider">
                        <Sparkles size={12} />
                        AI synthesized draft rationale
                      </div>
                      <p className="text-sm text-slate-200 italic leading-relaxed">
                        "{result.ai_explanation_draft}"
                      </p>
                    </div>

                    {/* Evidence Citations */}
                    <div className="space-y-3">
                      <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block">
                        Source Memos & Citations ({result.evidence.length})
                      </span>

                      {result.evidence.length === 0 ? (
                        <div className="text-center py-6 border border-slate-800 border-dashed rounded-2xl text-xs text-slate-500">
                          No document citations retrieved.
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {result.evidence.map((ev, i) => (
                            <div key={i} className="p-4 bg-slate-900 border border-slate-800 hover:border-slate-750 rounded-xl space-y-3 transition-colors">
                              <div className="flex justify-between items-center text-xs">
                                <span className="font-semibold text-blue-400 flex items-center gap-1">
                                  <FileText size={12} />
                                  {ev.company} ({ev.sector})
                                </span>
                                <span className="bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
                                  Sim: {(ev.similarity * 100).toFixed(1)}% | Page {ev.page}
                                </span>
                              </div>
                              <p className="text-xs text-slate-400 leading-relaxed font-mono whitespace-pre-line bg-slate-950/50 p-2.5 rounded border border-slate-850">
                                {ev.content}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-slate-800 bg-slate-950 flex justify-end">
              <button
                onClick={onClose}
                className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm transition-colors shadow-sm"
              >
                Close Audit Logs
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

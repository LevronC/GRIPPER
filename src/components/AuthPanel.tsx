import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronRight, Fingerprint, KeyRound, Lock, Mail } from 'lucide-react';
import { apiUrl, parseApiError } from '../lib/api';
import { routes } from '../lib/routes';
import { useStore } from '../store/useStore';

type Mode = 'login' | 'invite' | 'forgot' | 'reset';

/**
 * Secrets arrive in the URL fragment (#invite=… / #reset=…), which browsers never send
 * to servers or in Referer headers. They are read once and removed from the address bar.
 */
function readFragmentToken(): { mode: Mode; token: string } | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  for (const mode of ['invite', 'reset'] as const) {
    const token = params.get(mode);
    if (token) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
      return { mode, token };
    }
  }
  return null;
}

const inputClass =
  'w-full bg-white/[0.03] border border-white/10 rounded-2xl py-3 px-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 transition-all';
const labelClass = 'text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2 px-1';

export default function AuthPanel() {
  const { login, isLoading } = useStore();
  const [initial] = useState(readFragmentToken);
  const [mode, setModeState] = useState<Mode>(initial?.mode ?? 'login');
  const [token] = useState(initial?.token ?? '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const setMode = (next: Mode) => {
    setError('');
    setModeState(next);
  };

  const post = async (path: string, body: unknown, fallback: string) => {
    const res = await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await parseApiError(res, fallback));
    return res.json().catch(() => ({}));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (mode === 'login') {
        const result = await login(email, password);
        if (!result.ok) setError(result.error || 'Sign-in failed.');
      } else if (mode === 'invite') {
        await post('/auth/invitations/accept', { token, email, password }, 'Invitation could not be accepted.');
        setNotice('Account created. Sign in with your new password.');
        setPassword('');
        setMode('login');
      } else if (mode === 'forgot') {
        const data = await post('/auth/password-reset/request', { email }, 'Password reset is unavailable.');
        setNotice(data.message ?? 'If an account exists for that email, a reset link has been sent.');
      } else {
        await post('/auth/password-reset/confirm', { token, new_password: password }, 'Reset link is invalid or expired.');
        setNotice('Password updated. Sign in with your new password.');
        setPassword('');
        setMode('login');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed.');
    } finally {
      setBusy(false);
    }
  };

  const titles: Record<Mode, string> = {
    login: 'Sign in',
    invite: 'Accept invitation',
    forgot: 'Reset password',
    reset: 'Choose a new password',
  };
  const needsEmail = mode !== 'reset';
  const needsPassword = mode !== 'forgot';

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-[#05070A] font-sans text-slate-100 relative overflow-hidden">
      <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-cyan-600/10 blur-[150px]" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] rounded-full bg-blue-600/10 blur-[150px]" />

      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-[420px] mx-4 bg-[#0A0D14]/90 backdrop-blur-3xl border border-white/5 p-10 rounded-[2.5rem] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)] z-10"
      >
        <div className="text-center mb-10">
          <div className="mx-auto w-16 h-16 bg-gradient-to-tr from-cyan-500 to-blue-600 rounded-3xl flex items-center justify-center mb-6">
            <Fingerprint size={32} className="text-white" />
          </div>
          <h2 className="text-3xl font-black tracking-tighter text-white mb-2">
            GRIPPER<span className="text-cyan-400 font-normal">.terminal</span>
          </h2>
          <p className="text-xs text-slate-500 font-medium uppercase tracking-[0.2em]">{titles[mode]}</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          {mode === 'invite' && (
            <p className="text-[11px] text-slate-400 leading-relaxed px-1">
              Enter the email address the invitation was sent to and choose a password (at least 12 characters).
            </p>
          )}
          {needsEmail && (
            <div className="space-y-2">
              <label htmlFor="auth-email" className={labelClass}>
                <Mail size={12} className="text-cyan-500/70" /> Email
              </label>
              <input id="auth-email" type="email" required autoComplete="email" value={email}
                onChange={(e) => setEmail(e.target.value)} className={inputClass} />
            </div>
          )}
          {needsPassword && (
            <div className="space-y-2">
              <label htmlFor="auth-password" className={labelClass}>
                {mode === 'login' ? <Lock size={12} className="text-cyan-500/70" /> : <KeyRound size={12} className="text-cyan-500/70" />}
                {mode === 'login' ? 'Password' : 'New password'}
              </label>
              <input id="auth-password" type="password" required
                minLength={mode === 'login' ? undefined : 12}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
            </div>
          )}

          {error && (
            <div role="alert" className="p-4 bg-red-500/5 border border-red-500/20 text-red-400 rounded-2xl text-[11px] font-medium leading-relaxed">
              {error}
            </div>
          )}
          {notice && (
            <div role="status" className="p-4 bg-cyan-500/5 border border-cyan-500/20 text-cyan-400 rounded-2xl text-[11px] font-medium leading-relaxed">
              {notice}
            </div>
          )}

          <button type="submit" disabled={busy || isLoading}
            className="w-full py-4 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white rounded-2xl text-sm font-black tracking-wide transition-all flex items-center justify-center gap-3">
            {busy || isLoading ? (
              <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>{titles[mode]} <ChevronRight size={18} /></>
            )}
          </button>
        </form>

        <div className="text-center mt-8 space-y-3 text-[11px] font-bold tracking-wider uppercase">
          {mode === 'login' ? (
            <button type="button" onClick={() => setMode('forgot')} className="text-slate-500 hover:text-cyan-400 transition-colors">
              Forgot password?
            </button>
          ) : (
            <button type="button" onClick={() => setMode('login')} className="text-slate-500 hover:text-cyan-400 transition-colors">
              Back to sign in
            </button>
          )}
          <p className="text-slate-600 normal-case tracking-normal font-medium">
            Accounts are created by invitation from your institution's administrator.
          </p>
          <div className="flex justify-center gap-6">
            <Link to={routes.home} className="text-slate-500 hover:text-cyan-400 transition-colors">← Back to site</Link>
            <Link to={routes.docs} className="text-slate-500 hover:text-cyan-400 transition-colors">Documentation</Link>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

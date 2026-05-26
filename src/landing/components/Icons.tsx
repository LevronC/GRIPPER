import type { ReactNode } from 'react'

type IconProps = { className?: string }

export function ShieldIcon({ className = 'w-6 h-6' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2l8 4v6c0 5-3.5 9.5-8 10-4.5-.5-8-5-8-10V6l8-4z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function LockIcon({ className = 'w-6 h-6' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="5" y="11" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M8 11V8a4 4 0 118 0v3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function KeyIcon({ className = 'w-6 h-6' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="8" cy="12" r="4" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M12 12h8m-3-3v6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function SupportIcon({ className = 'w-6 h-6' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 14a8 8 0 1116 0v2a2 2 0 01-2 2h-1v-4h4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="2" y="11" width="4" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <rect x="18" y="11" width="4" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

const trustIcons: Record<string, (props: IconProps) => ReactNode> = {
  shield: ShieldIcon,
  lock: LockIcon,
  key: KeyIcon,
  support: SupportIcon,
}

export function TrustIcon({ name, className }: { name: string; className?: string }) {
  const Icon = trustIcons[name] ?? ShieldIcon
  return <Icon className={className} />
}

export function PhoneMockup() {
  return (
    <div className="relative mx-auto w-full max-w-[320px]">
      <div className="phone-glow absolute inset-0 -z-10 scale-110 blur-2xl" />
      <div className="rounded-[2.5rem] border border-white/10 bg-surface-elevated p-3 shadow-2xl shadow-black/40">
        <div className="overflow-hidden rounded-[2rem] bg-canvas">
          <div className="flex items-center justify-between px-5 py-3 text-xs text-ink-muted">
            <span>Live</span>
            <span className="font-medium text-ink">
              GRIPPER<span className="text-accent">.terminal</span>
            </span>
            <span className="text-accent">●</span>
          </div>
          <div className="space-y-4 px-5 pb-8 pt-2 text-left">
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Net Asset Value', value: '$4.28M', change: '+12.4%' },
                { label: 'Risk Exposure', value: '32.4%', change: '-2.1%' },
              ].map((stat) => (
                <div key={stat.label} className="rounded-xl border border-white/5 bg-white/5 p-3">
                  <p className="text-[10px] uppercase tracking-wide text-ink-muted">{stat.label}</p>
                  <p className="mt-1 text-sm font-semibold text-ink">{stat.value}</p>
                  <p className="text-xs text-accent">{stat.change}</p>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-red-400/20 bg-red-400/10 p-3">
              <p className="text-[10px] uppercase tracking-wide text-red-300">Open violation</p>
              <p className="mt-1 text-sm font-medium text-ink">Sector exposure cap — Technology</p>
              <p className="mt-1 text-xs text-ink-muted">34.2% vs 30% IPS limit</p>
            </div>

            <div className="rounded-xl border border-white/5 bg-white/5 p-3">
              <p className="text-[10px] uppercase tracking-wide text-accent">Research citation</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                CapEx guidance suggests increased infrastructure spend — see Axiom Dynamics memo, p. 12.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {[
                { sym: 'AAPL', w: '8.2%' },
                { sym: 'NVDA', w: '11.4%' },
                { sym: 'JPM', w: '6.1%' },
                { sym: 'Cash', w: '4.8%' },
              ].map((item) => (
                <div
                  key={item.sym}
                  className="rounded-lg border border-white/5 bg-white/5 px-3 py-2"
                >
                  <p className="text-sm font-medium">{item.sym}</p>
                  <p className="text-xs text-ink-muted">{item.w}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

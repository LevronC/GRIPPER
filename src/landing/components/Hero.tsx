import { Link } from 'react-router-dom'
import { hero } from '../data/content'
import { terminalPath } from '../../lib/routes'
import { PhoneMockup } from './Icons'

export function Hero() {
  return (
    <section id="platform" className="relative scroll-mt-28 overflow-hidden bg-canvas pt-28 section-pad lg:pt-36">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        aria-hidden="true"
        style={{
          background:
            'radial-gradient(ellipse 80% 50% at 50% -10%, rgba(56,189,248,0.25), transparent)',
        }}
      />

      <div className="container-wide relative grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
        <div className="reveal text-center lg:text-left">
          <p className="mb-4 text-sm font-medium uppercase tracking-[0.2em] text-accent">
            {hero.eyebrow}
          </p>
          <h1 className="font-display fluid-display font-normal text-ink">{hero.title}</h1>
          <p className="mx-auto mt-6 max-w-xl fluid-subhead text-ink-muted lg:mx-0">
            {hero.subtitle}
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4 lg:justify-start">
            <Link
              to={terminalPath('login')}
              className="pill-btn min-w-[160px] bg-accent text-accent-ink shadow-lg shadow-accent/25 hover:bg-accent-bright"
            >
              {hero.cta}
            </Link>
            <a
              href="#capabilities"
              className="pill-btn min-w-[160px] border border-white/15 bg-transparent text-ink hover:border-white/30"
            >
              {hero.secondary}
            </a>
          </div>
        </div>

        <div className="reveal lg:justify-self-end" style={{ animationDelay: '120ms' }}>
          <PhoneMockup />
        </div>
      </div>
    </section>
  )
}

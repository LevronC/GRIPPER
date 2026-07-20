import { Link } from 'react-router-dom'
import { proTier } from '../data/content'
import { terminalPath } from '../../lib/routes'

export function ProSection() {
  return (
    <section id="institutions" className="section-pad bg-canvas-warm">
      <div className="container-wide">
        <div className="max-w-3xl reveal">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-accent">
            {proTier.eyebrow}
          </p>
          <h2 className="mt-3 font-display fluid-headline font-normal text-ink">{proTier.title}</h2>
          <p className="mt-5 fluid-subhead text-ink-muted">{proTier.subtitle}</p>
          <Link
            to={terminalPath('register')}
            className="pill-btn mt-8 bg-accent text-accent-ink hover:bg-accent-bright"
          >
            {proTier.cta}
          </Link>
        </div>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {proTier.perks.map((perk, index) => (
            <article
              key={perk.title}
              className="reveal rounded-[1.5rem] border border-white/8 bg-surface p-6"
              style={{ animationDelay: `${index * 70}ms` }}
            >
              <h3 className="font-display text-lg tracking-tight text-ink">{perk.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-muted">{perk.body}</p>
            </article>
          ))}
        </div>

        <p className="mt-10 text-xs leading-relaxed text-ink-muted/70">
          Institutional deployments require PostgreSQL with pgvector, Redis for async workers, and
          configured RLS policies per tenant. See documentation for setup details.
        </p>
      </div>
    </section>
  )
}

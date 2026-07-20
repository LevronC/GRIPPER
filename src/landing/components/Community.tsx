import { Link } from 'react-router-dom'
import { community, trustGrid } from '../data/content'
import { terminalPath } from '../../lib/routes'
import { TrustIcon } from './Icons'

export function Community() {
  return (
    <section className="section-pad bg-surface">
      <div className="container-wide text-center reveal">
        <h2 className="font-display fluid-headline font-normal text-ink">{community.title}</h2>
        <p className="mx-auto mt-5 max-w-2xl fluid-subhead text-ink-muted">{community.subtitle}</p>
        <Link
          to={terminalPath('login')}
          className="pill-btn mt-10 bg-accent text-accent-ink hover:bg-accent-bright"
        >
          {community.cta}
        </Link>
      </div>
    </section>
  )
}

export function TrustSection() {
  return (
    <section id="security" className="section-pad bg-band">
      <div className="container-wide">
        <h2 className="font-display fluid-headline text-center font-normal text-ink reveal">
          {trustGrid.title}
        </h2>
        <div className="mt-14 grid gap-8 sm:grid-cols-2">
          {trustGrid.items.map((item, index) => (
            <article
              key={item.title}
              className="reveal flex gap-5 rounded-[1.5rem] border border-white/8 bg-canvas/40 p-6"
              style={{ animationDelay: `${index * 80}ms` }}
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
                <TrustIcon name={item.icon} />
              </div>
              <h3 className="text-lg leading-snug text-ink">{item.title}</h3>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

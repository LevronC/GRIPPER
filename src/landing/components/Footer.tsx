import { Link } from 'react-router-dom'
import { footerColumns } from '../data/content'
import { routes } from '../../lib/routes'

function FooterLinkItem({ label, href, external }: { label: string; href: string; external?: boolean }) {
  const className =
    'text-sm text-accent-ink/70 transition-colors hover:text-accent-ink hover:underline'

  if (external || href.startsWith('http') || href.startsWith('/api')) {
    return (
      <a href={href} className={className} target="_blank" rel="noopener noreferrer">
        {label}
      </a>
    )
  }

  if (href.startsWith('/#') || href.startsWith('#')) {
    return (
      <a href={href} className={className}>
        {label}
      </a>
    )
  }

  return (
    <Link to={href} className={className}>
      {label}
    </Link>
  )
}

export function Footer() {
  return (
    <footer className="bg-band-light text-accent-ink">
      <div className="section-pad pb-8">
        <div className="container-wide">
          <div className="grid gap-10 border-b border-accent-ink/10 pb-12 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <Link to={routes.home} className="font-display text-2xl tracking-tight">
                GRIPPER<span className="text-accent">.terminal</span>
              </Link>
              <p className="mt-4 max-w-xs text-sm leading-relaxed text-accent-ink/70">
                Multi-tenant investment compliance and semantic intelligence for institutional
                research teams and student equity programs.
              </p>
            </div>
            {footerColumns.map((col) => (
              <div key={col.title}>
                <h3 className="text-sm font-semibold">{col.title}</h3>
                <ul className="mt-4 space-y-2">
                  {col.links.map((link) => (
                    <li key={`${col.title}-${link.label}`}>
                      <FooterLinkItem {...link} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-10 space-y-4 text-[13px] leading-relaxed text-accent-ink/60">
            <p>
              GRIPPER is an investment compliance and research intelligence platform. Portfolio data,
              IPS rules, and uploaded research are processed within institution-scoped tenants.
              Not investment advice.
            </p>
            <p>
              Built for educational equity research programs. See{' '}
              <Link to={routes.docs} className="underline hover:text-accent-ink">
                documentation
              </Link>{' '}
              for setup, authentication, and API reference.
            </p>
          </div>

          <p
            className="pointer-events-none mt-12 select-none font-display text-[clamp(4rem,18vw,12rem)] font-semibold leading-none tracking-tighter text-accent-ink/8"
            aria-hidden="true"
          >
            GRIPPER
          </p>
        </div>
      </div>
    </footer>
  )
}

import { Link } from 'react-router-dom'
import { BrandLogo } from './BrandLogo'
import { routes, terminalPath } from '../../lib/routes'

type SiteHeaderProps = {
  scrolled?: boolean
}

export function SiteHeader({ scrolled = true }: SiteHeaderProps) {
  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        scrolled ? 'border-b border-white/5 bg-canvas/85 backdrop-blur-xl' : 'bg-transparent'
      }`}
    >
      <div className="container-wide flex items-center justify-between gap-4 px-[clamp(1.25rem,4vw,4rem)] py-4">
        <BrandLogo />
        <div className="flex items-center gap-4 text-sm">
          <Link to={routes.home} className="text-ink-muted transition-colors hover:text-ink">
            Home
          </Link>
          <Link to={routes.docs} className="hidden text-ink-muted transition-colors hover:text-ink sm:inline">
            Docs
          </Link>
          <Link
            to={terminalPath('login')}
            className="pill-btn bg-accent text-accent-ink shadow-lg shadow-accent/20 hover:bg-accent-bright"
          >
            Open terminal
          </Link>
        </div>
      </div>
    </header>
  )
}

import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { navLinks } from '../data/content'
import { BrandLogo } from '../../components/ui/BrandLogo'
import { routes, terminalPath } from '../../lib/routes'

export function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        scrolled ? 'border-b border-white/5 bg-canvas/85 backdrop-blur-xl' : 'bg-transparent'
      }`}
    >
      <div className="container-wide flex items-center justify-between gap-4 px-[clamp(1.25rem,4vw,4rem)] py-4">
        <BrandLogo />

        <nav className="hidden items-center gap-8 lg:flex" aria-label="Primary">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm text-ink-muted transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
          <Link
            to={routes.docs}
            className="text-sm text-ink-muted transition-colors hover:text-ink"
          >
            Docs
          </Link>
        </nav>

        <div className="hidden items-center gap-3 sm:flex">
          <Link
            to={terminalPath('login')}
            className="text-sm text-ink-muted transition-colors hover:text-ink"
          >
            Log in
          </Link>
          <Link
            to={terminalPath('register')}
            className="pill-btn bg-accent text-accent-ink shadow-lg shadow-accent/20 hover:bg-accent-bright"
          >
            Open terminal
          </Link>
        </div>

        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 lg:hidden"
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="sr-only">Menu</span>
          <div className="flex flex-col gap-1.5">
            <span className="block h-0.5 w-5 bg-ink" />
            <span className="block h-0.5 w-5 bg-ink" />
          </div>
        </button>
      </div>

      {menuOpen && (
        <div className="border-t border-white/5 bg-canvas/95 px-6 py-6 backdrop-blur-xl lg:hidden">
          <nav className="flex flex-col gap-4" aria-label="Mobile">
            {navLinks.map((link) => (
              <a key={link.label} href={link.href} className="text-base text-ink">
                {link.label}
              </a>
            ))}
            <Link to={routes.docs} className="text-base text-ink">
              Docs
            </Link>
            <div className="mt-4 flex flex-col gap-3 border-t border-white/10 pt-4">
              <Link to={terminalPath('login')} className="text-ink-muted">
                Log in
              </Link>
              <Link to={terminalPath('register')} className="pill-btn bg-accent text-accent-ink">
                Open terminal
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  )
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { productTabs } from '../data/content'
import { terminalPath } from '../../lib/routes'

export function Products() {
  const [active, setActive] = useState(productTabs[0].id)
  const current = productTabs.find((tab) => tab.id === active) ?? productTabs[0]

  return (
    <section id="capabilities" className="section-pad bg-accent text-accent-ink">
      <div className="container-wide">
        <div className="mb-10 flex flex-wrap gap-2 sm:gap-3">
          {productTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActive(tab.id)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-all sm:px-5 sm:py-2.5 ${
                active === tab.id
                  ? 'bg-accent-ink text-accent shadow-md'
                  : 'bg-accent-ink/10 text-accent-ink/80 hover:bg-accent-ink/15'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="grid items-end gap-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="reveal">
            <h2 className="font-display fluid-headline font-normal">{current.title}</h2>
            <p className="mt-5 max-w-xl fluid-subhead text-accent-ink/75">{current.body}</p>
            <Link
              to={terminalPath('login')}
              className="pill-btn mt-8 border border-accent-ink/20 bg-transparent text-accent-ink hover:bg-accent-ink/5"
            >
              Explore capability
            </Link>
          </div>

          <div
            className="reveal rounded-[2rem] border border-accent-ink/10 bg-accent-ink/5 p-8 backdrop-blur-sm"
            style={{ animationDelay: '100ms' }}
          >
            <div className="space-y-4">
              {productTabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActive(tab.id)}
                  className={`flex w-full items-center justify-between rounded-2xl px-4 py-3 text-left transition-all ${
                    tab.id === active ? 'bg-accent-ink text-accent' : 'text-accent-ink/70'
                  }`}
                >
                  <span className="font-medium">{tab.label}</span>
                  <span className="text-sm opacity-70">→</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

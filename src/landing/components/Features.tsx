import { Link } from 'react-router-dom'
import { enhanceSectionTitle, featureBlocks, enhanceCards } from '../data/content'
import { terminalPath } from '../../lib/routes'

export function Features() {
  return (
    <>
      {featureBlocks.map((block, index) => (
        <section
          key={block.title}
          className={`section-pad ${block.accent ? 'bg-surface' : 'bg-canvas-warm'}`}
        >
          <div
            className={`container-wide grid items-center gap-12 lg:grid-cols-2 ${
              index % 2 === 1 ? 'lg:[&>*:first-child]:order-2' : ''
            }`}
          >
            <div className="reveal">
              <h2 className="font-display fluid-headline font-normal text-ink">{block.title}</h2>
              <p className="mt-5 max-w-lg fluid-subhead text-ink-muted">{block.body}</p>
              <Link
                to={terminalPath('login')}
                className="pill-btn mt-8 bg-accent text-accent-ink hover:bg-accent-bright"
              >
                {block.cta}
              </Link>
            </div>
            <div className="reveal flex justify-center lg:justify-end">
              <div className="w-full max-w-md rounded-[2rem] border border-white/5 bg-surface-elevated/60 p-8">
                <div className="mb-6 flex flex-wrap gap-2">
                  {block.previewTags.map((label) => (
                    <span
                      key={label}
                      className="rounded-full border border-white/10 px-3 py-1 text-xs text-ink-muted"
                    >
                      {label}
                    </span>
                  ))}
                </div>
                <div className="space-y-3 text-left">
                  {block.previewItems.map((item) => (
                    <div key={item.label} className="rounded-xl bg-white/5 p-4">
                      <p className="text-xs text-accent">{item.label}</p>
                      <p className="mt-1 text-sm text-ink">{item.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      ))}

      <section id="workflow" className="section-pad bg-accent text-accent-ink">
        <div className="container-wide">
          <h2 className="font-display fluid-headline max-w-3xl font-normal">
            {enhanceSectionTitle}
          </h2>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {enhanceCards.map((card, index) => (
              <article
                key={card.title}
                className="reveal rounded-[1.75rem] border border-accent-ink/10 bg-accent-ink/5 p-6 backdrop-blur-sm"
                style={{ animationDelay: `${index * 60}ms` }}
              >
                <h3 className="font-display text-xl tracking-tight">{card.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-accent-ink/75">{card.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}

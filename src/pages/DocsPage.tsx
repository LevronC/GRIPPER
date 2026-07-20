import { Link } from 'react-router-dom'
import { routes } from '../lib/routes'

const sections = [
  {
    id: 'overview',
    title: 'Overview',
    body: 'GRIPPER (Gripper Risk Terminal) is a multi-tenant investment compliance and semantic intelligence platform. It automates Investment Policy Statement (IPS) checks, semantic research search over analyst PDFs, and portfolio governance monitoring for student equity programs such as RGIP and institutional research teams.',
  },
  {
    id: 'architecture',
    title: 'Architecture',
    body: 'The stack combines a React + TypeScript frontend, FastAPI backend, PostgreSQL with pgvector, and Redis Queue workers for async document ingestion.',
    items: [
      'Frontend: React 19, TypeScript, Tailwind CSS, Zustand, Framer Motion',
      'Backend: FastAPI, SQLAlchemy 2.0, Alembic migrations',
      'Database: PostgreSQL 16+ with pgvector extension and Row-Level Security (RLS)',
      'Workers: Redis + RQ for PDF parsing, chunking, and embedding jobs',
    ],
  },
  {
    id: 'auth',
    title: 'Authentication',
    body: 'Registration requires a valid .edu email address. After signup, verify your account with the 6-digit code printed to the backend console in development (or delivered by email in production). Login issues a JWT stored in localStorage as gripper_token.',
    items: [
      'POST /auth/register — create account (requires institution_id, role, .edu email)',
      'POST /auth/verify — confirm email with 6-digit code',
      'POST /auth/login — receive JWT access token',
      'POST /auth/logout — revoke token via Redis blacklist',
    ],
  },
  {
    id: 'roles',
    title: 'User roles',
    items: [
      'analyst — upload research, run semantic search',
      'sector_lead / pm — manage holdings and compliance evaluation',
      'faculty / trustee / admin — elevated governance access',
    ],
  },
  {
    id: 'setup',
    title: 'Local development setup',
    items: [
      '1. Create PostgreSQL database and enable CREATE EXTENSION vector;',
      '2. Set DATABASE_URL and REDIS_URL in backend/.env',
      '3. cd backend && pip install -r requirements.txt && alembic upgrade head',
      '4. uvicorn app.main:app --port 8000 --reload (with PYTHONPATH=.)',
      '5. python app/workers/worker.py in a separate terminal',
      '6. npm install && npm run dev from project root (proxies /api → :8000)',
    ],
  },
  {
    id: 'api',
    title: 'Key API endpoints',
    items: [
      'GET /institutions — list tenants (public for signup dropdown)',
      'GET /portfolios — list portfolios for current institution',
      'POST /portfolios/{id}/evaluate — run IPS compliance check',
      'POST /documents/upload — queue PDF ingestion (analyst+ roles)',
      'POST /search/semantic — pgvector similarity search over research chunks',
      'GET /health — service health check',
    ],
  },
  {
    id: 'rls',
    title: 'Row-Level Security',
    body: 'Every authenticated request sets SET LOCAL app.current_institution_id from the JWT user record. PostgreSQL RLS policies filter all tenant tables automatically, preventing cross-institution data leakage even if application code omits a filter.',
  },
  {
    id: 'environment',
    title: 'Environment variables',
    items: [
      'DATABASE_URL — PostgreSQL connection string',
      'REDIS_URL — Redis connection for RQ workers and token blacklist',
      'SECRET_KEY — JWT signing key',
      'VITE_API_BASE_URL — frontend API base (defaults to /api in dev)',
    ],
  },
]

export default function DocsPage() {
  return (
    <div className="landing-theme min-h-svh bg-canvas text-ink">
      <header className="border-b border-white/5 bg-canvas/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <Link to={routes.home} className="font-display text-xl tracking-tight">
            GRIPPER<span className="text-accent">.terminal</span>
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <Link to={routes.home} className="text-ink-muted hover:text-ink">
              Home
            </Link>
            <Link to={routes.terminalLogin} className="text-accent hover:text-accent-bright">
              Open terminal
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-16">
        <h1 className="font-display text-4xl tracking-tight md:text-5xl">Documentation</h1>
        <p className="mt-4 max-w-2xl text-ink-muted">
          Reference for developers and program administrators running GRIPPER locally or in
          production.
        </p>

        <nav className="mt-10 flex flex-wrap gap-2" aria-label="Documentation sections">
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="rounded-full border border-white/10 px-3 py-1.5 text-sm text-ink-muted transition-colors hover:border-accent/40 hover:text-ink"
            >
              {section.title}
            </a>
          ))}
        </nav>

        <div className="mt-14 space-y-14">
          {sections.map((section) => (
            <section key={section.id} id={section.id} className="scroll-mt-24">
              <h2 className="font-display text-2xl tracking-tight">{section.title}</h2>
              {section.body && (
                <p className="mt-4 leading-relaxed text-ink-muted">{section.body}</p>
              )}
              {section.items && (
                <ul className="mt-4 space-y-2 text-sm leading-relaxed text-ink-muted">
                  {section.items.map((item) => (
                    <li key={item} className="rounded-xl border border-white/5 bg-white/5 px-4 py-3">
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>

        <div className="mt-16 rounded-2xl border border-accent/20 bg-accent/10 p-6">
          <h3 className="font-display text-xl">Interactive API reference</h3>
          <p className="mt-2 text-sm text-ink-muted">
            When the backend is running locally, FastAPI auto-generates OpenAPI docs.
          </p>
          <a
            href={routes.apiDocs}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-bright"
          >
            Open API docs
          </a>
        </div>
      </main>
    </div>
  )
}

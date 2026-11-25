/** Landing copy for GRIPPER — investment compliance & institutional intelligence. */

export const navLinks = [
  { label: 'Platform', href: '#platform' },
  { label: 'Capabilities', href: '#capabilities' },
  { label: 'Institutions', href: '#institutions' },
  { label: 'Workflow', href: '#workflow' },
  { label: 'Security', href: '#security' },
]

export const hero = {
  eyebrow: 'Investment compliance terminal',
  title: 'Compliance and research intelligence, in one terminal.',
  subtitle:
    'GRIPPER automates Investment Policy Statement checks, semantic research search, and portfolio governance — built for student equity programs and institutional research teams.',
  cta: 'Open terminal',
  secondary: 'See capabilities',
}

export const productTabs = [
  {
    id: 'governance',
    label: 'IPS Governance',
    title: 'Catch policy breaches before the boardroom does',
    body: 'Deterministic rules engine for single-position caps, sector exposure limits, and liquidity constraints — evaluated on demand against saved or hypothetical holdings.',
  },
  {
    id: 'rag',
    label: 'Research RAG',
    title: 'Search analyst memos with semantic precision',
    body: 'Upload PDF research, then search it by meaning and keyword (pgvector plus PostgreSQL full-text, fused with Reciprocal Rank Fusion). Results show the source document and page.',
  },
  {
    id: 'monitoring',
    label: 'Portfolio Monitoring',
    title: 'Holdings with violation tracking',
    body: 'Track holdings, allocated weight, and open and resolved compliance violations in one dashboard, and test hypothetical trades before committing them.',
  },
  {
    id: 'tenancy',
    label: 'Multi-Tenant RLS',
    title: 'True isolation between institutions',
    body: 'Every institution\'s data is isolated twice: by ownership checks in application code and independently by PostgreSQL Row-Level Security, through a database role that cannot bypass it.',
  },
  {
    id: 'ingestion',
    label: 'Async Ingestion',
    title: 'Upload once, process in the background',
    body: 'Redis-backed workers parse, chunk, and embed documents asynchronously where a worker is available; failed uploads are kept and can be retried.',
  },
]

export const featureBlocks = [
  {
    accent: true,
    title: 'Every violation comes with related research',
    body: 'When a portfolio breaches IPS limits, GRIPPER states the breach in plain terms and surfaces related passages from your uploaded research, with document and page, for analysts to review. Research never changes a violation\'s status.',
    cta: 'See explanations',
    previewTags: ['Violations', 'Citations', 'IPS'],
    previewItems: [
      {
        label: 'Sector exposure alert',
        text: 'Technology exposure is 34.2%; the sector limit is 30.0%. This violation is open. (Illustrative example.)',
      },
      {
        label: 'Research citation',
        text: '“Capital expenditure guidance implies higher infrastructure concentration…” — synthetic research note, p. 12.',
      },
    ],
  },
  {
    accent: false,
    title: 'Bridge structured portfolios with unstructured research',
    body: 'GRIPPER connects holdings data, governance rules, and analyst documents in one pipeline — from PDF ingestion through hybrid search to reconciliation of resolved violations on each evaluation.',
    cta: 'Explore the pipeline',
    previewTags: ['Ingest', 'Search', 'Reconcile'],
    previewItems: [
      {
        label: 'Semantic query',
        text: 'Search: “regulatory review risk” — matching passages ranked by Reciprocal Rank Fusion, with page references.',
      },
      {
        label: 'Compliance reconciler',
        text: 'Violations that no longer apply are marked resolved on the next evaluation, and kept in the history.',
      },
    ],
  },
]

export const enhanceCards = [
  {
    title: 'Upload research PDFs',
    body: 'PDF signature and size validation, page-preserving chunking, and embedding when a provider is configured; memos become searchable without manual tagging.',
  },
  {
    title: 'Automated IPS rule evaluation',
    body: 'Single-position caps, sector limits, and micro-cap liquidity rules run deterministically whenever a portfolio is evaluated or a scenario is simulated.',
  },
  {
    title: 'Institution-scoped workspaces',
    body: 'Each institution is its own isolated tenant with role-based access and invitation-only membership.',
  },
  {
    title: 'Explanations on every alert',
    body: 'Open any violation to see the rule, the values that breached it, and related passages from your research library, labelled as a rule-based explanation.',
  },
  {
    title: 'Built for student-managed funds',
    body: 'Designed for student-managed investment funds and similar research teams that operate under an investment policy statement.',
  },
  {
    title: 'Audit-ready violation history',
    body: 'Track open and resolved compliance events with timestamps — ready for faculty review and program accountability.',
  },
]

export const proTier = {
  eyebrow: 'Built for institutions',
  title: 'GRIPPER Institutional',
  subtitle:
    'Everything student research programs and multi-cohort equity teams need — hardened tenancy, async ingestion, and governance automation out of the box.',
  cta: 'Request institutional access',
  perks: [
    {
      title: 'PostgreSQL Row-Level Security',
      body: 'Transaction-scoped tenant context enforced by the database, in addition to application-level ownership checks, and verified by integration tests that use the restricted runtime role.',
    },
    {
      title: 'pgvector semantic search',
      body: 'Native vector similarity over document chunks powers research Q&A with institution-scoped retrieval only.',
    },
    {
      title: 'Deterministic IPS evaluator',
      body: 'Position caps, sector exposure limits, and liquidity constraints evaluated with transparent, auditable rule logic.',
    },
    {
      title: 'Async RQ ingestion workers',
      body: 'Decoupled PDF parsing and embedding jobs keep the terminal responsive during heavy upload periods.',
    },
    {
      title: 'Compliance reconciler & audit log',
      body: 'Background loop tracks, resolves, and archives violations while preserving historic governance events.',
    },
  ],
}

export const community = {
  title: 'Built for the next generation of institutional analysts',
  subtitle:
    'From student-managed portfolios to faculty oversight — GRIPPER gives research teams the compliance rigor markets demand and the speed boardrooms expect.',
  cta: 'Launch the terminal',
}

export const trustGrid = {
  title: 'Institutional-grade security by design',
  items: [
    {
      title: 'Database-level tenant isolation with PostgreSQL RLS on every query.',
      icon: 'shield',
    },
    {
      title: 'Session-scoped institution context prevents cross-cohort data access.',
      icon: 'lock',
    },
    {
      title: 'Role-based access, invitation-only accounts, and single-use, expiring password-reset links.',
      icon: 'key',
    },
    {
      title: 'Full governance audit trail for violations, resolutions, and research uploads.',
      icon: 'support',
    },
  ],
}

export type FooterLink = {
  label: string
  href: string
  external?: boolean
}

export const footerColumns: { title: string; links: FooterLink[] }[] = [
  {
    title: 'Platform',
    links: [
      { label: 'IPS Governance', href: '/#capabilities' },
      { label: 'Research RAG', href: '/#capabilities' },
      { label: 'Portfolio Monitoring', href: '/#capabilities' },
      { label: 'Explainability', href: '/#workflow' },
      { label: 'API Docs', href: '/api/docs', external: true },
    ],
  },
  {
    title: 'Institutions',
    links: [
      { label: 'Multi-Tenant RLS', href: '/#institutions' },
      { label: 'Cohort Workspaces', href: '/#institutions' },
      { label: 'Student-managed funds', href: '/#workflow' },
      { label: 'Documentation', href: '/docs' },
      { label: 'Open Terminal', href: '/app?mode=login' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Privacy', href: '/docs#environment' },
      { label: 'Data Handling', href: '/docs#rls' },
      { label: 'Compliance Disclosures', href: '/docs#overview' },
      { label: 'Setup Guide', href: '/docs#setup' },
    ],
  },
]

export const enhanceSectionTitle = 'How research teams use GRIPPER'

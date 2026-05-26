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
    body: 'Deterministic rules engine for single-position caps, sector exposure limits, and liquidity constraints — evaluated continuously against live holdings.',
  },
  {
    id: 'rag',
    label: 'Research RAG',
    title: 'Search analyst memos with semantic precision',
    body: 'Upload PDF research, chunk and embed it with pgvector, then ask questions about CapEx, risk factors, or guidance with citations from your own documents.',
  },
  {
    id: 'monitoring',
    label: 'Portfolio Monitoring',
    title: 'Live holdings with violation tracking',
    body: 'Track NAV, risk exposure, alpha signals, and open compliance alerts in a single dashboard built for high-stress review sessions.',
  },
  {
    id: 'tenancy',
    label: 'Multi-Tenant RLS',
    title: 'True isolation between institutions',
    body: 'PostgreSQL Row-Level Security keeps Stetson, UF, and every cohort separated at the database layer — not just in application code.',
  },
  {
    id: 'ingestion',
    label: 'Async Ingestion',
    title: 'Upload once, process in the background',
    body: 'Redis-backed workers parse, chunk, and embed documents asynchronously so uploads never block your research workflow.',
  },
]

export const featureBlocks = [
  {
    accent: true,
    title: 'Every violation comes with a cited explanation',
    body: 'When a portfolio breaches IPS limits, GRIPPER generates compliance alerts backed by passages from your uploaded research — so analysts can defend decisions with evidence, not guesswork.',
    cta: 'See explainability',
    previewTags: ['Violations', 'Citations', 'IPS'],
    previewItems: [
      {
        label: 'Sector exposure alert',
        text: 'Technology weight is 34.2%, exceeding the 30% IPS limit. See memo excerpt on CapEx-driven concentration risk.',
      },
      {
        label: 'Research citation',
        text: '“Fiscal 2027 CapEx of $1.8B for distributed inference pipelines increases infrastructure concentration…” — Axiom Dynamics 10-K, p. 12.',
      },
    ],
  },
  {
    accent: false,
    title: 'Bridge structured portfolios with unstructured research',
    body: 'GRIPPER connects holdings data, governance rules, and analyst documents in one pipeline — from PDF ingestion through vector search to automated reconciliation of resolved violations.',
    cta: 'Explore the pipeline',
    previewTags: ['Ingest', 'Search', 'Reconcile'],
    previewItems: [
      {
        label: 'Semantic query',
        text: 'Ask: “What did we write about regulatory review risk in Q3?” — results ranked by similarity with page references.',
      },
      {
        label: 'Compliance reconciler',
        text: 'Resolved violations are archived automatically while preserving a full audit trail for program review.',
      },
    ],
  },
]

export const enhanceCards = [
  {
    title: 'Upload research PDFs in seconds',
    body: 'Magic-byte validation, clean semantic chunking, and async embedding — your memos become searchable without manual tagging.',
  },
  {
    title: 'Automated IPS rule evaluation',
    body: 'Single-position caps, sector limits, and micro-cap liquidity rules run deterministically against every portfolio update.',
  },
  {
    title: 'Institution-scoped workspaces',
    body: 'Each cohort gets its own isolated tenant with role-based access, preserving proprietary thesis documents between programs.',
  },
  {
    title: 'Explainability on every alert',
    body: 'Open the drawer on any violation to see severity, rule type, and RAG-backed justification pulled from your research library.',
  },
  {
    title: 'Built for RGIP-style programs',
    body: 'Designed for Roland George Investments Program boardroom gauntlets and student-managed equity research workflows.',
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
      body: 'Session-scoped tenant isolation enforced at the database engine — data leakage between institutions is structurally impossible.',
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
      title: 'Role-based authentication with secure token handling and verification flows.',
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
      { label: 'RGIP Programs', href: '/#workflow' },
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

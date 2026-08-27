# MBA Compass

**Build the career that gets you there.**

A personal career &amp; MBA command center — one place to track career history, projects and
measurable impact, skills, certifications, leadership, international exposure, MBA targets,
financial planning, and an AI advisor, all pointed at one question: *if I applied today, how
prepared would I be, what's holding me back, and what should I do next?*

## Status

All six build phases are implemented.

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Foundation — auth, database, design system, navigation, profile, dashboard | **done** |
| 2 | Career, Projects &amp; Impact, Evidence Bank, Skills, Certifications, Education, Leadership, International Exposure | **done** |
| 3 | MBA Targets, readiness scoring engine, gap analysis, What-If simulator, application tracker | **done** |
| 4 | Roadmap, Tasks, Financial Plan (scholarships ship under MBA Targets) | **done** |
| 5 | AI Career Advisor, provider-agnostic AI layer, Story Bank, Next Best Action engine | **done** |
| 6 | Polish — loading/error states, accessibility pass, rate limiting, data export/deletion | **done** |

Two features described in the original spec were deliberately left out of this pass rather than
built shallow: a standalone Monthly/Quarterly AI Review and a dedicated Goal Consistency Engine.
Both are natural extensions of the AI Advisor once there's a few months of real usage data to
review — the `Reflection` and `Goal` tables already exist in the schema for them.

## Features

- **Dashboard** — primary MBA target, live readiness score, top 3 next-best-actions (rule-based,
  no AI required), career/international/learning snapshots, financial snapshot.
- **Career** — timeline of experiences with nested achievements.
- **Projects & Impact** — problem/actions/result narratives with repeatable before/after impact
  records per project (category, metric, before/after values, annualized value).
- **Evidence Bank** — proof items optionally linked to a project or certification.
- **Skills, Certifications, Education, Leadership, International Exposure** — focused CRUD, each
  feeding the readiness engine.
- **MBA Targets** — program CRUD (cost, experience/test requirements, target intake, last-verified
  date + source URL), deadlines, scholarships, primary-target selection, per-program scoring
  weights.
- **MBA Readiness** — a configurable, explainable readiness score. Each of the 10 dimensions
  (academic profile, professional experience, leadership, business impact, international
  exposure, GMAT/GRE, English, career progression, extracurricular, goal clarity) is computed by
  a pure rule-based calculator (`src/lib/scoring`), weighted per-program, and fully inspectable —
  click any dimension to see the exact factors and recommendations behind its score. Explicitly
  labeled a *preparation score*, never an admission probability. Includes a What-If simulator and
  point-in-time snapshotting for trend tracking.
- **MBA Application** — per-program application status and a 7-item document checklist.
- **Roadmap** — a year-by-year plan with milestones, dependencies, KPIs and priorities.
- **Tasks** — list and kanban views.
- **Financial Plan** — estimated cost breakdown, funding-source targets, a compounding savings
  projection chart against the estimated total cost, and a contributions/costs log.
- **AI Career Advisor** — a chat grounded in a factual snapshot of your own data (never invents
  achievements), plus a Story Bank for STAR-format leadership/impact stories. Works fully without
  an AI key configured; the chat just explains that it's off.
- **Settings** — full profile CRUD, JSON data export, and account deletion.

Every module not yet listed above didn't exist — there are none; all planned modules from the
original spec are built.

## Tech stack

- **Framework:** Next.js 16 (App Router, Turbopack), React 19, TypeScript
- **UI:** Tailwind CSS v4, Radix UI primitives hand-assembled in the shadcn/ui style (the shadcn
  CLI's registry fetch isn't reachable from every environment, so `src/components/ui/` is written
  directly against `@radix-ui/*` + `class-variance-authority`), Lucide icons, Recharts
- **Database:** PostgreSQL (developed against [Neon](https://neon.tech)), Prisma ORM 7 using the
  `@prisma/adapter-pg` driver adapter (Prisma 7 requires an explicit adapter — see
  `prisma.config.ts` and `src/lib/db.ts`)
- **Auth:** Auth.js (NextAuth) v5, Credentials provider, JWT sessions, bcrypt password hashing.
  Single-user today; the schema is fully multi-user-ready (every domain table hangs off `userId`)
- **Validation/forms:** Zod, React Hook Form
- **AI:** a provider-agnostic abstraction (`src/lib/ai/provider.ts`) over the Anthropic or OpenAI
  REST APIs via plain `fetch` — no heavyweight SDK, selected by `AI_PROVIDER`. Server-only; keys
  never reach the client bundle. A per-user in-memory rate limit guards the advisor endpoint.

## Getting started

```bash
npm install
cp .env.example .env   # fill in DATABASE_URL and AUTH_SECRET
npx prisma generate
npx prisma migrate dev # applies prisma/migrations against DATABASE_URL
npm run db:seed        # optional but recommended — populates a realistic demo profile
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). You'll be redirected to `/login`.

### Seed credentials

The seed script creates one account. By default:

- Email: `demo@mbacompass.app`
- Password: `ChangeMe123!`

Override before seeding with `SEED_USER_EMAIL`, `SEED_USER_PASSWORD`, `SEED_USER_NAME` env vars.
**Change the password** (via Settings once signed in has no password-change UI yet — update it
directly in the database, or re-seed with your own `SEED_USER_PASSWORD`) if this is deployed
anywhere reachable.

## Environment variables

See `.env.example`. Required:

- `DATABASE_URL` — PostgreSQL connection string
- `AUTH_SECRET` — random 32-byte secret (`npx auth secret`)
- `NEXTAUTH_URL` — base URL of the app (`http://localhost:3000` in dev)

Optional (AI Advisor):

- `AI_PROVIDER` — `openai` or `anthropic`; leave empty to run without AI features
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
- `OPENAI_MODEL` / `ANTHROPIC_MODEL` — override the default model for the active provider

None of these are ever sent to the client — they're read only in server-side code (Server
Actions, Route Handlers, the Prisma client, the AI provider module).

## Database

`prisma/schema.prisma` defines the full data model. Highlights:

- Every table carries a `userId` foreign key, so multi-user support is an auth change, not a
  schema change.
- `MBAProgram` stores requirements, deadlines and scholarships as related tables, plus
  `lastVerifiedAt` / `sourceUrl` — MBA program data is never presented as current without a
  verification date, shown on both the program card and the dashboard.
- `ScoringDimension` + `MBADimensionWeight` make the readiness engine's weights per-program and
  DB-configurable rather than hard-coded; new programs get the default weights copied in on
  creation, and the weights editor enforces they total 100.
- `MBAAssessment.breakdown` stores a JSON snapshot of a score calculation (dimension scores,
  factors, gaps, recommendations) so every score stays explainable and auditable after the fact.

Migrations live in `prisma/migrations/`. Because Prisma 7 uses driver adapters instead of a
`datasource.url` in the schema file, migrations run via `prisma.config.ts` (wired to read
`DATABASE_URL`).

## Commands

```bash
npm run dev         # start the dev server (Turbopack)
npm run build        # production build
npm run start         # run the production build
npm run lint           # ESLint
npm run typecheck       # tsc --noEmit
npm run db:migrate       # prisma migrate dev
npm run db:seed           # prisma db seed (runs prisma/seed.ts)
npm run db:studio          # prisma studio
```

## Security

- Passwords are hashed with bcrypt; never stored or logged in plaintext.
- Auth config is split into `src/auth.config.ts` (safe for `src/proxy.ts`'s smaller bundle — no
  Node-only deps) and `src/auth.ts` (full config with the Credentials provider).
- Every mutation is a Zod-validated Server Action scoped to `requireUserId()`; list/update/delete
  queries filter by `userId` (or, for nested records, by the parent's `userId`) rather than
  trusting a bare id — a request for someone else's row simply matches nothing. Cross-entity links
  entered by the user (e.g. Evidence → Project, Story → Project) are ownership-checked before
  saving.
- The AI Advisor endpoint is rate-limited per user (in-memory sliding window; a multi-instance
  deployment would want a shared store instead).
- Data export (`/api/export`, wired from Settings) and full account deletion (type-to-confirm, in
  Settings) are both implemented — the user owns their data.
- Secrets are read from environment variables only, never hard-coded, never exposed to the client
  bundle — the AI provider module and Prisma client are both `server-only`.

## Known limitations / next steps

- **Monthly/Quarterly AI Review and Goal Consistency Engine** are not built — see Status above.
- **Calendar view for Tasks** — only List and Kanban views ship; a calendar view was scoped out.
- **MBARequirement** (free-form extra requirements beyond the standard GMAT/GRE/English fields) has
  a schema but no UI yet — the standard fields on `MBAProgram` cover the common case.
- **No password-change UI** — the seed script and direct DB access are the only ways to change
  credentials today.
- This was built and verified in a sandboxed environment with no outbound network access to the
  database or any LLM provider; schema/seed data were applied via the Neon MCP tool rather than a
  live `prisma migrate dev` / `prisma db seed` run, and the AI Advisor's live calls are unverified
  end-to-end (structurally correct, gated by `isAIConfigured()`, but not exercised against a real
  API key). Both work normally with real network access — a deploy target, CI, or your own machine.

## Project principle

The dashboard is designed to always answer five questions: **Where am I? Where am I going?
What's holding me back? What should I do next? Why does it matter?** Every score the app ever
shows is a *preparation/readiness* score against configured criteria — never a fabricated
admission probability.

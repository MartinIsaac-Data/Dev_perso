# MBA Compass

**Build the career that gets you there.**

A personal career &amp; MBA command center — one place to track career history, projects and
measurable impact, skills, certifications, leadership, international exposure, MBA targets,
financial planning and an AI advisor, all pointed at one question: *if I applied today, how
prepared would I be, what's holding me back, and what should I do next?*

This is a long-term, phased build. See [Status](#status) for what's implemented today.

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Foundation — auth, database, design system, navigation, profile, dashboard skeleton | **done** |
| 2 | Career, Projects &amp; Impact, Evidence Bank, Skills, Certifications, Education | planned |
| 3 | MBA Targets, readiness scoring engine, gap analysis, What-If simulator | planned |
| 4 | Roadmap, Goals, Tasks, Financial Plan, Scholarship tracker | planned |
| 5 | AI Career Advisor, Monthly/Quarterly Review, Story Builder, Goal Consistency Engine | planned |
| 6 | Polish — responsiveness, accessibility, empty/loading/error states, hardening | planned |

Every other nav item currently renders a clearly-labeled "on the roadmap" placeholder rather
than a 404 or fake data.

## Tech stack

- **Framework:** Next.js 16 (App Router, Turbopack), React 19, TypeScript
- **UI:** Tailwind CSS v4, Radix UI primitives (hand-assembled in the shadcn/ui style — the
  shadcn CLI's registry fetch isn't reachable from every environment, so the components in
  `src/components/ui/` are written directly against `@radix-ui/*` + `class-variance-authority`),
  Lucide icons, Recharts (charts arrive in Phase 3+)
- **Database:** PostgreSQL (developed against [Neon](https://neon.tech)), Prisma ORM 7 using the
  `@prisma/adapter-pg` driver adapter (Prisma 7 requires an explicit adapter — see
  `prisma.config.ts` and `src/lib/db.ts`)
- **Auth:** Auth.js (NextAuth) v5, Credentials provider, JWT sessions, bcrypt password hashing.
  Single-user today; the schema is fully multi-user-ready (every domain table hangs off `userId`)
- **Validation/forms:** Zod, React Hook Form
- **AI:** not yet wired up (Phase 5). The env vars for a provider-agnostic OpenAI/Anthropic
  abstraction are already reserved (`AI_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

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
**Change the password** (via the database, or once a settings-level credential change ships) if
this is deployed anywhere reachable.

## Environment variables

See `.env.example`. Required:

- `DATABASE_URL` — PostgreSQL connection string
- `AUTH_SECRET` — random 32-byte secret (`npx auth secret`)
- `NEXTAUTH_URL` — base URL of the app (`http://localhost:3000` in dev)

Optional (AI Advisor, Phase 5):

- `AI_PROVIDER` — `openai` or `anthropic`; leave empty to run without AI features
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`

None of these are ever sent to the client — they're read only in server-side code (Server
Actions, Route Handlers, the Prisma client).

## Database

`prisma/schema.prisma` defines the full data model up front (all phases), even though the UI for
later-phase entities doesn't exist yet — this avoids destructive schema churn as phases land.
Highlights:

- Every table carries a `userId` foreign key, so multi-user support is an auth change, not a
  schema change.
- `MBAProgram` stores requirements, deadlines and scholarships as related tables, plus
  `lastVerifiedAt` / `sourceUrl` — MBA program data is never presented as current without a
  verification date.
- `ScoringDimension` + `MBADimensionWeight` make the (Phase 3) readiness engine's weights
  per-program and DB-configurable rather than hard-coded.
- `MBAAssessment.breakdown` stores a JSON snapshot of a score calculation (dimension scores,
  factors, gaps, recommendations) so every score stays explainable and auditable after the fact.

Migrations live in `prisma/migrations/`. Because Prisma 7 uses driver adapters instead of a
`datasource.url` in the schema file, run migrations via `prisma.config.ts` (already wired to read
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
- Auth config is split into `src/auth.config.ts` (edge/proxy-safe — no Node-only deps) and
  `src/auth.ts` (full config with the Credentials provider); `src/proxy.ts` uses only the former.
- All mutations go through Zod-validated Server Actions; nothing trusts client input directly.
- Secrets are read from environment variables only, never hard-coded, never exposed to the
  client bundle.

## Project principle

The dashboard is designed to always answer five questions: **Where am I? Where am I going?
What's holding me back? What should I do next? Why does it matter?** Every score the app ever
shows is a *preparation/readiness* score against configured criteria — never a fabricated
admission probability.

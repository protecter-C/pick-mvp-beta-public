# PICK MVP Repository Instructions

## Product

PICK is a purchase decision, protection, and reward app.

Primary flow: product URL/search/share -> deterministic BUY, WAIT, or PASS verdict with evidence -> price tracking -> purchase -> points -> satisfaction -> Choice Score -> repeat.

## MVP scope

- Authentication, profile, and purchase preferences.
- Product URL/search input, product details, and alternatives.
- Deterministic BUY/WAIT/PASS scoring. An LLM may only parse intent or explain a verdict; it must never determine the score, verdict, or rank.
- Price history, target prices, and alert preferences.
- Purchases with post-purchase satisfaction, return-window, and warranty tracking.
- Append-only points ledger, rewards, and referrals.
- Choice Score from 0-100 using value, fit, timing, and satisfaction.
- Savings, prevented spend, decision history, and dashboard metrics.
- In-app notification records and replaceable delivery adapters.

## Product integrity rules

- Reward good WAIT and PASS decisions when appropriate; never make spending the preferred way to earn rewards.
- Affiliate or sponsor revenue must never affect verdicts, evidence, alternatives, scores, or rank.
- Keep product, price, affiliate, notification, and optional LLM integrations behind replaceable interfaces. Use deterministic mock providers in the MVP.
- Preserve existing code and user changes. Build a modular monolith and avoid premature distributed-system complexity.

## Stack and structure

- `apps/mobile`: Flutter client.
- `apps/web`: Next.js TypeScript client.
- `services/api`: FastAPI Python modular monolith.
- PostgreSQL with pgvector is the production database target; Redis is the production cache/job target.
- The local/test MVP may use SQLite and in-memory adapters so it runs without external infrastructure.
- Shared API behavior is defined by the FastAPI OpenAPI contract; avoid duplicating business rules in clients.

## Engineering rules

- Work autonomously in small phases.
- After each phase, run relevant tests, lint, or typecheck and fix failures before continuing.
- Add dependencies only when necessary.
- Keep deterministic scoring pure, explainable, and thoroughly tested.
- Store money as integer minor units and timestamps in UTC.
- Points are an append-only ledger; balances are derived, never directly mutated.
- Keep secrets out of the repository and provide `.env.example` values only.
- Prefer narrow modules with explicit provider protocols over framework-wide abstractions.

## Progress format

During implementation, user-facing progress updates contain only these markers:

`[PHASE] name`

`[DONE] ...`

`[TEST] pass/fail`

`[NEXT] ...`

`[BLOCKED] ...` only when blocked.

The final handoff includes changed files, tests run, and remaining production integrations.

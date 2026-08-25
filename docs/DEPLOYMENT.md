# Deployment

The single authoritative deployment runbook. Supersedes `DEPLOYMENT-CHECKLIST.md` and
`FIREBASE-SETUP.md` at the repo root, which predate the current Netlify/GitHub Actions
architecture and drifted out of sync with it (both retain a pointer to this file now rather
than being deleted, in case their historical detail is useful).

## Architecture

- **Frontend**: static Vite/React SPA, built with `npm run build` (output `dist/`), deployed
  to **Netlify**. `netlify.toml` sets the build command, Node 22, and a catch-all SPA redirect.
- **Auth + data**: **Firebase** (Authentication + Firestore). Only `firestore.rules` is
  managed via `firebase.json` — there is no Firebase Hosting or Cloud Functions deployment;
  serverless functions run on **Netlify Functions** (`netlify/functions/`) instead.
- **Research pipeline**: Python, runs on a schedule via **GitHub Actions**
  (`.github/workflows/refresh-advisor.yml`), commits its output (`public/data/`,
  `pipeline/pit_store/`, `pipeline/shadow_store/`, `pipeline/reports/`) back to the repo.
  Netlify then serves whatever is currently committed under `public/data/` — there is no
  separate data-serving backend.

## Environment variables

See `.env.example` for the full list with inline explanations. Two categories:

- **`VITE_*` prefixed** — bundled into the client at build time and shipped to every
  browser. This includes `VITE_FIREBASE_*`. **This is expected and correct, not a leak**:
  Firebase's web SDK config (API key, project ID, etc.) is not a secret — it identifies which
  Firebase project a request targets, and access control is enforced entirely by
  `firestore.rules` and Firebase Auth, not by hiding this config. Restrict the key's allowed
  origins/APIs in the Firebase/Google Cloud console as defense in depth, but do not treat it
  as a credential to protect like a private key.
- **Everything else** — server-only, read by Netlify Functions or GitHub Actions.
  **Never** prefix these with `VITE_`; doing so would bundle them into the client build.
  `GITHUB_REFRESH_TOKEN`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `VAPID_PRIVATE_KEY`, and
  `ALERT_DELIVERY_SECRET` are true secrets and must only ever be set in Netlify's/GitHub's
  environment variable stores, never committed.

## Netlify functions

Three functions, each independently authenticated:

- `refresh-data.mjs` — Firebase ID token + `REFRESH_ALLOWED_EMAILS` allowlist. Dispatches and
  polls the `refresh-advisor.yml` GitHub Actions workflow via `GITHUB_REFRESH_TOKEN`. Accepts
  `symbols` (dispatched as `portfolio_symbols` — the caller's holdings) and `focus_symbols`
  (dispatched as `focus_symbols` — re-poll and re-rank exactly these names and nothing else,
  used by the theme screen's re-rank button). The two are separate because the portfolio list
  also drives portfolio coverage and tags theme rows as holdings.
- `portfolio-prices.mjs` — Firebase ID token. Proxies Yahoo quotes (including post-market) so
  the browser never calls Yahoo directly.
- `alert-push.mjs` — shared secret (`ALERT_DELIVERY_SECRET`), called by the pipeline after a
  scored refresh via `ALERT_DELIVERY_URL`. Uses `firebase-admin` server-side, which reads
  `alerts/{uid}/subscriptions` directly and correctly bypasses `firestore.rules` — that is
  expected server-trust behavior, not a rules gap (rules govern client SDK access only).

## Uploading a holdings file

The Portfolio page's **Data actions → Upload holdings file** reads a JSON file and writes it to
Firestore. This is the general-purpose form of the baseline import: the same reconciliation,
driven by a file rather than a constant compiled into the bundle, so a new brokerage export
never needs a code change.

The file is parsed and planned entirely in the browser first (`src/lib/portfolioImport.js`,
pure and separately tested) and nothing is written until the plan on screen is confirmed. Two
modes, because one of them deletes:

- **Replace** — the file is the whole portfolio; holdings it omits are removed.
- **Merge** — add and update only.

Accepted shape is a JSON array of holdings, or an object with a `positions` array. Each holding
needs `ticker`, `shares`, and either `costBasisTotal` or `costBasis` (per share); `purchaseDate`
(`YYYY-MM-DD`), `price` and `value` are optional. Every problem in a file is reported at once
rather than one per attempt, and a repeated ticker is refused rather than silently resolved.
**Export portfolio** writes this same shape, so an export always imports back.

A current file is served at `/holdings/fidelity-2026-08-25.json` and is covered by a test that
fails if it stops matching the shipped baseline. An import stamps the reference-baseline marker,
so the built-in Fidelity baseline will not reconcile a deliberate upload away.

## Portfolio baseline sync (CLI)

`scripts/sync-portfolio-firebase.mjs` applies the Fidelity reference portfolio
(`src/lib/referencePortfolio.js`) straight to Firestore, for the cases that cannot wait on a
browser: seeding a fresh account, repairing one whose holdings drifted, or pushing a newly
exported baseline and confirming what it changes before it reaches the UI. The signed-in app
already reconciles itself once per `REFERENCE_PORTFOLIO_VERSION`; this is the same
reconciliation, run on demand.

```bash
npm run portfolio:sync -- --email you@example.com            # dry run — writes nothing
npm run portfolio:sync -- --email you@example.com --commit   # apply
npm run portfolio:sync -- --uid <uid> --commit               # by uid, skipping the Auth lookup
npm run portfolio:sync -- --email you@example.com --report portfolio-check.md
```

### Verification report (`--report`)

`--report <path>` writes a self-contained report — Markdown, or JSON if the path ends `.json`,
or `-` for stdout. It works on a dry run and after a commit, and answers two questions that
are easy to conflate:

- **Is the baseline correct?** Ten checks compare the shipped rows against
  `REFERENCE_PORTFOLIO_EXPECTED`, the figures transcribed from the Fidelity account summary
  and deliberately kept separate from the rows: position count, total cost, market value,
  value + money market against the account total, `shares × price = value` and
  `shares × cost/share = total cost` on every row, no money-market line tracked as a holding,
  no duplicate ticker, no purchase date taken from the export date, and only the expected
  holdings undated. Editing a holding without updating the brokerage totals fails these.
- **Is the account updated?** Field-level drift between what Firestore holds and what the
  sync would write — `shares: 0.5 → 0.101`, `purchaseDate: (none) → 2026-08-07` — plus adds,
  removals, and a full holdings table totalling to the brokerage account total. An account
  already holding the baseline reports "already matches this baseline" with no drift rows.

The report is the artifact to check against a statement, or to attach when someone asks
whether the stored portfolio is right.


Both paths share `planReferencePortfolioSync` and the record builders beside it, so they write
identical documents and cannot drift. A commit also stores the export's invested-only intraday
snapshot and stamps `tracking/state` with the baseline version, which stops the app from
re-running its own sync for that version.

**Dry run is the default**, because the import is authoritative: a stored holding absent from
the export is deleted, not left alone. The dry run prints every add, update and removal with
share counts, cost bases and acquisition dates.

### Credentials

`npm run portfolio:sync` loads `.env.local` if present, and picks a mode from what it finds:

- **Sign-in** (default). Uses the `VITE_FIREBASE_*` client config already there for
  `npm run dev`, plus the account's own app password — prompted for without echo, or read
  from `PORTFOLIO_SYNC_PASSWORD`. It is deliberately not a flag, which would leave the
  password in shell history. Writes go through `firestore.rules` exactly as the browser's
  would; the rules grant a signed-in user their own `portfolios/{uid}`, which is all this
  needs. Nothing extra to configure.
- **Admin**, when `FIREBASE_SERVICE_ACCOUNT_JSON` is set — the same service-account credential
  `alert-push.mjs` uses. No password, and it can sync any account, so it is the only mode that
  supports `--uid`. It bypasses `firestore.rules` by design: a server-side secret that must
  never take a `VITE_` prefix.

Every network step announces itself before it runs and is bounded at 30 seconds, so a blocked
connection names the step it stalled on instead of appearing to hang.

## Scheduled pipeline (GitHub Actions)

| Workflow | Schedule | What it does |
|---|---|---|
| `refresh-advisor.yml` | 07:00/12:00/15:00 ET, weekdays | Full sweep (07:00) or fast refresh (12:00/15:00); scores the universe, publishes `public/data/*`, commits back |
| `marketstack-premarket.yml` | 08:00/16:00 ET, weekdays | Premarket/intraday collection |
| `congress-trades.yml` | Monday ~08:00 ET | Weekly STOCK Act disclosure screen |
| `ci.yml` | every push to `main`, every PR | Lint, test, build, pipeline test/validate — `contents: read` only, never writes |
| `demo-data.yml` | manual only | Legacy congressional-signal demo path |

## Deploy steps (Netlify)

1. Connect the repo to a Netlify site; build command and publish directory come from
   `netlify.toml` automatically.
2. Set every `VITE_*` and server-only variable from `.env.example` in Netlify's site
   environment variables.
3. Set the same secrets referenced by `refresh-advisor.yml`
   (`FIREBASE_SERVICE_ACCOUNT_JSON`, provider API keys) as GitHub Actions repository secrets
   — these are a separate store from Netlify's.
4. Deploy `firestore.rules` via the Firebase CLI (`firebase deploy --only firestore:rules`)
   whenever `firestore.rules` changes — Netlify does not deploy this.
5. Confirm the scheduled workflows are enabled (GitHub disables scheduled workflows on forks
   and on repos idle for 60+ days).

## App Check

Not currently configured. Consider enabling Firebase App Check (reCAPTCHA v3 or App
Attest/Play Integrity) to reduce abusive traffic to Firestore/Auth from outside the deployed
app — this was evaluated as a recommendation, not implemented, in this pass.

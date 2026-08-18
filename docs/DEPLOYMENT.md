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

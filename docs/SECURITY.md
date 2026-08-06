# Security

## Audit findings (this pass)

A full secret scan across every tracked non-lock file found **no live credentials
committed**. `.env.example` was already correct: placeholder values only, and it correctly
distinguishes browser-safe `VITE_*` variables from server-only secrets (see
`docs/DEPLOYMENT.md`). The only string matches for `api_key=` are two hardcoded test
fixtures (`pipeline/tests/test_congress_trades.py`, `pipeline/tests/test_marketstack.py`),
both clearly fake values used only in unit tests.

**Fixed in this pass:** `.github/workflows/ci.yml` granted `permissions: contents: write` at
the workflow level but no step in either job ever writes or pushes — this ran on every PR,
including from forks. Changed to `contents: read`, the minimum this workflow actually needs.

## Firestore rules

`firestore.rules` scopes every user-owned collection
(`users`, `portfolios`, `finances`, `alerts`, `watchlists`) to
`request.auth.uid == userId`, recursively. Two intentionally broader rules, left as-is
because they are deliberate design choices, not oversights:

- `profiles/{userId}` is readable by any authenticated user (write remains owner-only) —
  intentional so a household sharing one deployment can see each other's profile cards.
- `backtestSignals/{signalId}` is readable by any authenticated user, writable only when
  `request.resource.data.userId == uid` — shared research artifacts, not private data.

`alert-push.mjs` reads `alerts/{uid}/subscriptions` via the `firebase-admin` SDK, which
correctly bypasses Firestore rules (rules apply to client SDK access; a trusted server using
the admin SDK is expected to have full access). Not a rules gap.

## Firebase web config

`VITE_FIREBASE_*` values are bundled into the client and visible in every page load. **This
is not a secret leak** — the Firebase web SDK config identifies a project, it does not grant
access on its own. Real access control lives entirely in `firestore.rules` and Firebase Auth.
Recommended hardening (not a requirement, since the config isn't sensitive): restrict the API
key's allowed HTTP referrers and enabled APIs in the Google Cloud Console.

## Rotation

No exposed or historically-committed sensitive key was found, so no rotation is required by
this audit. If a real secret is ever committed by mistake, treat it as compromised
immediately (rotate at the provider, then scrub history) rather than only removing it from
the latest commit — git history retains it until actively purged.

## App Check

Not configured. See `docs/DEPLOYMENT.md`'s App Check note — recommended, not implemented.

## Reporting

This is a research/personal-finance tool, not a service with a public bug-bounty program.
If you find a real vulnerability, open a private security advisory on the GitHub repository
rather than a public issue.

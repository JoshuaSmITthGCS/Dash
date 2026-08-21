# Canonical Transaction Event Schema

Master Remediation Prompt v3, roadmap item 6 — a schema-only deliverable, the stated prerequisite
for B3 (the tax-lot ledger). Full schema: `docs/schemas/transaction-event.schema.json`.

## Why this exists

This session built three real, working Firestore collections (`intradaySnapshots`, `activity`,
`rebalances` — see `src/lib/usePortfolioTracking.js`) to unblock items 2–4 (MWR/XIRR, turnover,
the reconciliation bridge). Each is deliberately narrow — exactly the fields its one consumer
needs, nothing more. That was the right call for those items: building a general transaction
model before any feature needed one would have been speculative infrastructure with no consumer
to validate it against.

B3 (the tax-lot ledger) is different: it is the first feature that genuinely needs a *general*
transaction record — one that carries lot identity, tax treatment, and a full timestamp
provenance chain, none of which the three narrow collections above have any reason to carry
today. Writing that general shape down now, before B3 is built, means B3's proposal (see
`docs/BUILD-PLAN.md`) can scope a real migration instead of guessing at one.

## What the schema adds beyond today's `activity` collection

| Concept | Today (`activity` collection) | Canonical schema |
|---|---|---|
| Event types | `realized_gain`, `dividend`, `fee`, `deposit`, `withdrawal` | Adds `buy`, `sell`, `interest`, `tax_withholding`, `split`, `spinoff`, `merger`, `transfer_in`, `transfer_out` |
| Security identity | None — `activity` rows are account-level, not security-level | `security_id` (provider-independent — FIGI/CUSIP/ISIN, never a bare ticker) |
| Tax treatment | Not modeled | `tax_treatment` per account |
| Lot tracking | None — `realized_gain` is a single pre-computed number per sale, average-cost only | `lot_selection_method` + `lots_affected[]`, with a `wash_sale_disallowed_loss` slot ready for B3's wash-sale engine |
| Timestamp provenance | `effectiveDate` + `recordedAt` only | Full B1 chain: `event_at`, `published_at`, `available_at`, `source_effective_at`, `observed_at`, `ingested_at`, `revised_at` + `supersedes_event_id` |
| Corrections | Overwritten in place (`setDoc` with a fixed id) | `supersedes_event_id` links a correction to the exact record it replaces, mirroring `pit_store.py`'s `diff_revisions` pattern on the pipeline side — never a silent overwrite |
| Corporate actions | Not modeled | `corporate_action_id` cross-references B4's independent ledger when a transaction was itself triggered by one |

## What is explicitly NOT built from this schema in this session

Per the Execution Contract's authorization tiers, this is a schema, not an engine. Nothing reads
or writes this shape yet. Building the actual lot-tracking engine, the migration off today's flat
`activity` collection, and the wash-sale logic is B3 — proposed with an effort estimate in
`docs/BUILD-PLAN.md`, explicitly not started, pending sign-off.

## Migration shape when B3 is authorized

Not a breaking change to what exists today — `deposit`/`withdrawal`/`dividend`/`fee`/`realized_gain`
activity rows map onto this schema's cash-event types directly (`security_id: null`,
`lots_affected: []`), so the existing MWR/XIRR, turnover, and reconciliation-bridge code built
this session keeps working unmodified against the same underlying data once (if) it's migrated
to write in the canonical shape. `buy`/`sell` events would newly need `security_id` resolution
(via OpenFIGI, not yet wired — see `docs/API-DATA-SOURCE-PLAN.md`) and lot creation logic that
does not exist anywhere in this codebase today.

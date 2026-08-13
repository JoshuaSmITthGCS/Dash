# Response to the ValueSignal Research-Score Evidence Audit — Factual Corrections

Reply to the 2026-08-10 external methodology audit. The audit's core statistical diagnosis
(within-block collinearity destroying effective breadth, fixed-band dispersion compression,
turnover on the wrong side of the Novy-Marx–Velikov 50% line) is accepted and is not disputed
here. This document corrects the claims the audit makes about this codebase that are factually
wrong or describe features as missing that are already implemented. Every correction cites the
live config or code, verified 2026-08-10.

---

## 1. "No point-in-time data spine exists" — false

The audit's headline architectural claim ("should not run real capital until a point-in-time
data spine … exist[s]", "the concrete migration: adopt a point-in-time spine … SEC EDGAR XBRL")
describes infrastructure that is already built and running:

- **Raw fundamentals PIT store** — `pipeline/data/pit/observations.jsonl` (~9,800 observation
  rows at audit date), plus `revisions.jsonl`, `fundamental_restatements.jsonl` (restatement
  log), and `universe.jsonl` (universe-membership log, survivorship defense). Every observation
  carries `observed_at`, `observation_date`, `source`.
- **Cutoff semantics** — `as_of()` implementations at `pipeline/pit_store.py:235` and
  `pipeline/edgar_facts.py:218` never return a value observed after a given cutoff.
- **EDGAR is already the fundamentals source of record** — the audit recommends "SEC EDGAR XBRL
  … as the fundamentals of record … keep yfinance for prices only." The live config already
  does this: `metric_registry.json::declaration_defaults.preferred_providers` is
  `["sec_xbrl", "alpha_vantage", "yahoo"]`. Yahoo is the *last-resort* statement provider, not
  the primary one.
- **Scored validation PIT** — `pipeline/pit_store/YYYY-MM-DD.jsonl`, immutable per-(refresh,
  ticker) rows with `config_hash`, `model_version`, and realized forward returns.

**What the audit should have said:** the PIT architecture exists but has no *historical depth* —
it accumulates as-filed values forward from inception only, so any **backtest** still runs on
restated history. The correct remediation is an EDGAR Financial Statement Data Sets *backfill*
into the existing store, not a migration to a store that already exists. The distinction
matters: it changes the work from an architecture project to a data-loading project.

## 2. "Stop using with real capital until an out-of-sample IC record exists — a hard gate" — already the repo's own stated policy

The audit presents this as its remediation item (a)(2). It is the codebase's existing,
documented gate: `minimum_icir_periods = 24`, zero periods observed, **no signal promoted**,
and the model card's own classification ("no demonstrated residual alpha") — all stated in
`docs/MASTER-METHODOLOGY.md` §9, which the audit itself quotes. The delta of this
recommendation is zero. Crediting it as a finding overstates the audit's contribution and
understates the repo's existing discipline.

## 3. Sector conditioning "missing entirely" — overstated

The audit lists sector-neutralization as absent ("EV/EBITDA and P/B are meaningless without
industry conditioning"). Partially implemented:

- Band mode uses **per-sector bands**: `settings.json::fundamentals` carries
  `forward_pe_by_sector`, `price_to_sales_by_sector`, and related per-sector configurations.
- The cross-sectional challenger scores each metric against the **sector distribution when ≥8
  peers exist** (`CrossSectionalNormalizer`, `scorer.py:296-450`), falling back to the full
  universe otherwise.
- **Financial-sector exemption**: bank/insurer snapshots drop 12 inapplicable metrics from the
  coverage denominator entirely (`FINANCIAL_EXEMPT`, `scorer.py:167-170`).
- The **sector valuation percentile modifier** (±3.0) is explicitly sector-relative, not
  absolute.

What is genuinely missing is full sector-neutralization of the *composite* (residualizing the
final score against sector membership). That is a fair finding. "Missing entirely" is not.

## 4. "Downweight accruals" — already done, with the audit's own rationale

The accruals ratio carries 22% of a 10% block ≈ **1.7% of the total score**, and the
methodology doc states the reason verbatim: "the accruals-ratio anomaly has decayed in US data
since 2002, so it's a minor input, not the bucket." The audit recommends what the config
already encodes, citing the same decay literature.

## 5. The investment/CMA factor is not missing — the audit missed where it lives

The audit warns the growth block "risks the wrong sign versus the investment literature"
(high-asset-growth firms underperform). The repo already implements the CMA-consistent
treatment: **asset growth is scored as an `ideal_range` metric that penalizes aggressive
growth** (`derive_asset_growth`, `fundamentals_extended.py:360-371`, documented as
"Fama-French investment factor: aggressive asset growth predicts *lower* subsequent returns"),
sitting in the capital-allocation block at 22%. The growth block's raw revenue/EPS growth
metrics are a fair target — but the claim that the model has a naive wrong-signed growth tilt
ignores that the offsetting investment factor is present and correctly signed.

## 6. "Keep congressional/13F strictly shadow-only" — they already are

Both are computed via `apply_challenger_modifiers()` (`advisor_engine.py:399-487`) and are
**not** part of the production ±15-point modifier stack. They allocate from a separate
challenger cap and never touch the published score. The recommendation describes the current
state.

## 7. "Keep news sentiment at ≤4% or drop it" — it is at 4%, cut from 10%, for the audit's own cited reason

`settings.json::ranking_weights` sets news at 0.04 with an inline comment citing Tetlock
(2007) headline-alpha decay — the same citation the audit uses. The audit acknowledges the cut
was "directionally right" but frames the weight as a live recommendation rather than a
completed decision.

## 8. Cross-sectional ranking framed as a missing feature — it is a built, published challenger

"Promote the challenger to champion" is a fair recommendation and the direction is accepted.
But the audit's framing ("fixed hand-set bands … are the wrong default") reads as if
winsorized cross-sectional percentile ranking needs to be built. It is fully implemented
(`CrossSectionalNormalizer`, winsorized percentiles, sector-conditional), published beside the
champion on every refresh, and awaiting promotion through the same prospective-evidence gate as
everything else. Promoting it on an auditor's argument alone would violate the exact
validation discipline the audit demands elsewhere. The challenger will be promoted when the
harness — not rhetoric — clears it.

## 9. Hysteresis "hinted at" — implemented, with configurable thresholds

The audit says the momentum screen's 90th/75th entry/exit "hints at" a buy/hold spread. It is
not a hint: `research_screens_v2.py:200-205` implements full entry/exit hysteresis with
configurable `entry_percentile` (90) and `exit_percentile` (75), including held-position
state. The correct and accepted finding is narrower: the **main composite score** lacks the
same mechanism. (Also noted: the audit's attribution of the 64.9% turnover to "the
technical/news components and fixed bands" is asserted, not measured — turnover decomposition
is future work, not an audit result.)

## 10. Survivorship bias treated as a discovery — it is self-disclosed, with a forward defense in place

The backtest's survivorship bias, approximated filing timestamps, and restated-data basis are
all self-reported in §9 of the methodology doc — the audit's own caveats section concedes every
headline number it grades on (−2.57% alpha, 64.9% turnover, regression loadings) is
"self-reported by the user and not independently verified." A universe-membership log
(`universe.jsonl`) already records membership prospectively so the bias cannot recur in
forward validation. The bias is real; the framing of it as an uncovered defect is not.

## 11. The "technical indicator zoo" concern is already engineered against

`technical_extended` is capped at four indicators from four distinct economic families
(trend/oscillator/volatility/volume), ~0.25% of the total score each, with a module docstring
explicitly citing the data-snooping literature as the reason for the cap. At ~1% of the total
score combined, it cannot be a material driver of any result the audit grades.

---

## What stands uncontested

For the record, the corrections above do not touch the audit's strongest findings, which are
accepted as the working roadmap:

1. **Collinearity/breadth diagnosis (audit Task 3)** — the fundamental-law argument that the
   null value/profitability loadings are *predicted* by five collinear valuation multiples,
   band-compressed dispersion, and dilution from weak metrics. This is the best analysis in
   the audit.
2. **Composite-level buy/hold hysteresis** — genuinely absent, highest impact per unit effort.
3. **Historical as-filed backfill** — the real version of the audit's data finding (§1 above).
4. **Valuation-block collapse** to two sector-neutralized enterprise multiples.
5. **MAX/idiosyncratic-volatility screen** — genuinely absent, cheap to add.
6. **No explicit risk model / portfolio-construction layer** — genuinely absent.
7. The 35 hand-set weights are unfalsifiable at current granularity (DeMiguel-Garlappi-Uppal).

The grain of salt, in short, belongs on the audit's architecture claims and its grading, not
on its math.

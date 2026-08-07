# P0 — Q3: Does selection bootstrapping cost real alpha?

**Skipped.** Stated reason: the required test — full statement enrichment for all 910 names,
compared against the production 150-name shortlist-gated ranking, with forward-return
measurement for names the shortlist excludes — needs live Yahoo Finance statement fetches for
the ~760 names never enriched today. This session's network egress policy blocks
`query1.finance.yahoo.com` (confirmed in `docs/P0-REPAIRS.md` WO-3/WO-2 via the proxy status
endpoint), and no local cache of full-universe statement data exists to substitute (only the
committed `public/data/advisor.json` screen universe, which is itself the already-gated 374-name
output this test needs to compare *against* an unconstrained run — using it as a stand-in for the
unconstrained side would be circular).

**Reproduction, once run from an environment with real internet access:**
```bash
ADVISOR_EXTENDED_LIMIT=910 python pipeline/fetch_advisor.py
```
This forces `enrich()` to run statement fetches for the full universe instead of the 150-name
shortlist (`pipeline/fetch_advisor.py:52,892`). Expect this to run far past the 90-minute
production budget and to consume the full Alpha Vantage daily quota many times over across
however many days it takes to stage (the brief anticipates exactly this — "Stage it across days
if needed and commit the accumulated artifact"). Once complete, `Spearman` the unconstrained
ranking against the production shortlist-gated ranking, count how many of the unconstrained
top 40 never entered the shortlist, and measure their forward returns against historical prices
already on disk.

**Priority, given WO-4's result.** The brief frames Q3 as mattering most if a fundamentals-first
process has "real selection skill buried under bad portfolio construction" — i.e., the payoff
from fixing the shortlist gate is largest when there is demonstrated alpha the gate is
suppressing. WO-4 (`docs/P0-Q1-BENCHMARK.md`) found no significant residual alpha net of the six
factors this model is built from (Newey-West |t| = 0.437), which is the leading evidence against
that scenario. This does **not** make Q3 uninteresting — a structural defect that biases the
input to every downstream layer is worth knowing about on its own terms, and it is possible the
gate suppresses alpha that would only become visible once found — but it does mean Q3 is no
longer the thing standing between this system and a demonstrated edge, and it should not be
prioritized over acting on WO-4's result. Carried into `docs/P0-VERDICT.md` as a skipped,
lower-priority item with a costed path to running it later.

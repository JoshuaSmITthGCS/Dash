# Screen Presets

Machine-readable registry: `pipeline/config/screen_presets.json`. All 16 presets from the
upgrade brief are declared. **7 are wired to a real, tested implementation; 9 are
specification-only** — the ranking rules and filters are documented but nothing computes
them yet. Every preset states which honestly via `implementation_status` and
`implemented_in`; a preset never claims "wired" without citing exactly where.

## Wired (7)

| Preset | Ranking | Implementation |
|---|---|---|
| Deep Value | FCF yield, EV/EBIT, PEG, P/B | `pipeline/sleeves/value.py` |
| Quality Value | value + quality composite | `pipeline/sleeves/value.py` + `quality.py`, `screens/quality-value.json` |
| Momentum Leaders | 12-1, 6-1, industry-relative momentum | `pipeline/research_screens_v2.py momentum_scores()` |
| Oversold Reversal | 5d/21d residual decline, RSI, volume | `src/lib/researchScreens.js rankReversal()` |
| Durable Growth | revenue/FCF growth, margin trend | `pipeline/sleeves/growth.py` |
| Insider Cluster Buying | routine vs opportunistic Form 4 | `pipeline/insider_signal.py` |
| Congressional Disclosure Activity | disclosure recency, magnitude | `pipeline/build_congress_screen.py` |

## Specification-only (9)

Emerging Momentum, High-Quality Recovery, Mean-Reversion Setup, GARP, Shareholder Yield,
Defensive Compounders, Trend Following, Earnings Revision Leaders, Balanced Multi-Factor.

Each of these has real, tested primitives it could be built from (the value/quality/growth
sleeves, `technical_indicators.py`'s Bollinger/RSI/moving-average-slope, the catalyst factor
table in `research_screens_v2.py`), but no combining/ranking function exists yet. Building
one is future work, not claimed as done here.

## Why declare the unbuilt ones at all

Because the brief and the final report both ask for the exact ranking and filter rules of
every preset — including the ones not yet implemented. A registry that only listed the 7
built ones would look complete while silently dropping 9 the brief specifically asked for.
Declaring all 16 with an honest status is the difference between a specification and a
performance claim.

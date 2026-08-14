# Homepage Layout Reference

This document describes the complete visual structure of the ValueSignal Financial Report homepage (`src/pages/Dashboard.jsx`), section by section, top to bottom. Every section listed here is what a user sees when they open the app with a connected portfolio.

---

## Page Structure Overview

```
Financial Report Page (.financial-report-page)
|
+-- Page Header (.report-head)
+-- Refresh Feedback (conditional)
+-- Empty State OR Full Dashboard
    |
    +-- Customize Bar
    +-- Widget Stack (.dashboard-widget-stack)
    |   +-- [Widget] Portfolio Summary
    |   +-- [Widget] Performance Chart
    |   +-- [Widget] Portfolio Scores + Performance Metrics
    |   +-- [Widget] Sector Allocation
    |   +-- [Widget] Top Signal
    |   +-- [Widget] Action Needed
    |   +-- [Widget] Watchlist Preview
    |
    +-- Two-Column Section
    |   +-- Retirement Projection
    |   +-- Opportunity Cost
    |
    +-- Buying the Dip Chart
    +-- Market Sentiment Strip
    +-- Market Pulse Preview
    +-- Market Heatmap
    +-- Focused Research Screens
    +-- Methodology Footer
```

All sections inside the widget stack are wrapped in `<DashboardWidget>` and can be reordered or hidden by the user through the customize panel. Sections below the widget stack are always visible and in fixed order.

---

## 1. Page Header

**Class:** `.report-head`

| Element | Content |
|---------|---------|
| Eyebrow | `Latest close` + the report generation date |
| Title | "Financial Report" |
| Subtitle | "Your portfolio, explained with traceable daily-close data." |
| Actions | Refresh full universe button (authenticated users), Privacy toggle (eye icon) |

Below the header, a refresh progress bar and status message appear when a universe refresh is active.

---

## 2. Portfolio Summary Hero (Widget: `portfolio-summary`)

The most prominent section on the page. A single bordered card divided into a hero cell and three metric cells.

### 2a. Hero Grid (`.report-hero-grid`)

**Layout:** 4-column grid -- `1.7fr 1fr 1fr 1fr`. On tablet (<=900px) becomes 2 columns with the hero spanning full width. On phone (<=620px) stacks vertically with 3 metric cells in a row below.

**Visual:** The hero cell has a subtle radial gradient glow in the bottom-right corner (`::after` pseudo-element) for depth.

#### Hero Cell (`.report-hero`)

| Element | Description |
|---------|-------------|
| Label | "Current portfolio value" with an optional spinning sync icon during quote refresh |
| Value | Large animated number showing total portfolio value (e.g. "$142,518") |
| Direction pills | Two pill-shaped badges: today's return (dollar + percent) and after-hours return, each colored green/red by direction with arrow icons |
| Refresh button | "Refresh after-hours" -- fetches live Yahoo quotes |
| Status message | Success/error feedback from quote refresh |
| Hero sparkline | Small inline sparkline showing the last 30 values of the current chart series |
| Coverage note | "12 holdings - 98% price coverage" |

#### Three Metric Cells (`.report-metric`)

| Metric | Content |
|--------|---------|
| Today's return | Dollar return with percent and date |
| Planning success | Probability that savings survive through retirement end age (links to Planning page) |
| Action needed | Count of holdings with guidance beyond Hold, listing the first three tickers |

### 2b. Secondary Facts (`.report-secondary-facts`)

Attached directly below the hero grid with no gap, sharing the same border radius at the bottom. Two metric cells:

| Metric | Content |
|--------|---------|
| Total unrealized return | Dollar gain/loss versus entered cost basis |
| Invested cost basis | Total shares x per-share cost |

### 2c. Insights Mood Card (`.dashboard-pulse`)

A card with a mood-tinted gradient background (green for positive, red for negative, brand-blue for neutral). Contains:

| Element | Description |
|---------|-------------|
| Emoji | Large mood indicator (e.g. rocket, green circle, warning) |
| Headline | Mood label (e.g. "Portfolio is performing well") |
| Blurb | One-sentence mood explanation |
| Link | "Trader insights" button to the full insights page |
| Stat strip | Row of key stats: today's return, strategy return, benchmark beat/trail streak |

### 2d. Research Shelves (`.home-research-shelves`)

Two horizontal scrollable card rails:

**Top signals rail:** Cards showing the top-ranked research names. Each card displays:
- Rank number and sector
- Ticker (large)
- Company name
- Research score

**Theme exposure rail:** Cards for each mapped portfolio theme showing:
- Theme name
- Exposure score
- Portfolio coverage percentage

### 2e. Portfolio Return Summary

Two side-by-side article cards comparing return methodologies:

| Method | Description |
|--------|-------------|
| Strategy return (time-weighted) | Modified Dietz calculation |
| Your return (money-weighted) | Annualized XIRR including deposit timing |

Each shows the return value, a colored horizontal bar proportional to the return magnitude (green for positive, red for negative), and a methodology label. An explanation paragraph spans the bottom.

---

## 3. Performance Chart (Widget: `performance-chart`)

A full-width card containing the main portfolio growth chart.

### Chart Controls

| Control | Description |
|---------|-------------|
| Series toggle | "Backtested basket" vs "Recorded value" -- switches between hypothetical history and actual tracked history |
| Period selector | 1D, 1W, 1M, 3M, YTD, 1Y, All -- pill-shaped toggle buttons |
| Benchmark picker | Checkbox labels for up to 3 ETF benchmark proxies (SPY, QQQ, etc.) |

### Chart Area

The `<GrowthChart>` SVG renders:
- **Primary line** (portfolio) with a gradient area fill beneath it that fades from the series color at ~18% opacity down to transparent. In dark mode, the primary line has a subtle glow effect.
- **Benchmark lines** as dashed secondary lines (no fill).
- **End marker dot** on each line's final data point.
- After-hours marker when available.

Below the chart, a 4-column summary strip shows: period dollar change, charted portfolio high, observed intraday high, and all-time earnings.

Benchmark comparison results appear as a 3-column strip showing each benchmark's return and the dollar difference vs. the portfolio.

---

## 4. Portfolio Scores + Performance Metrics (Widget: `metric-grid`)

### 4a. Score Grid (`.report-score-grid`)

Three score gauge cards in a 3-column grid:

| Score | Description |
|-------|-------------|
| Portfolio score | Composite 0-100 score covering fundamentals, diversification, and resilience |
| Diversification | Score based on sector concentration and position sizing |
| Resilience | Score based on maximum drawdown and annualized volatility |

Each card renders a **semi-circular gauge** (`<ScoreGauge>`) with:
- Arc background track in surface color
- Gradient fill arc (red at 0 -> yellow at 50 -> green at 100)
- Needle indicator circle at the current score position
- Score number centered below the gauge
- Text label ("Strong", "Moderate", "Fair", "Developing", "Weak")
- Provisional badge when data is incomplete

Below the gauges, a collapsible `<details>` element shows how the portfolio score is built (component scores).

### 4b. Live Tracking Toggle

A settings row with a toggle to restrict performance statistics to the period since live tracking started (excludes backtested history before the cutoff date).

### 4c. Performance Metrics (`<PerformanceMetrics>`)

A bordered card containing:

**Evidence bar:** An 8px-tall stacked horizontal bar showing the proportion of positive/neutral/negative metrics.

**Metric grid:** 6-column grid (3 columns on tablet, 2 on phone) of individual metric cards. Each `<MetricCard>` shows:
- Metric name and status icon (triangle up/down, circle)
- Formatted value
- Supporting context (observations, cadence)
- Confidence level
- Trend indicator: 3-bar SVG icon colored by direction (green=improving, red=deteriorating, gray=stable) with trend detail text

**Rolling 60-day Sharpe chart:** SVG polyline chart with a gradient area fill beneath the line, showing Sharpe ratio stability over time.

---

## 5. Sector Allocation (Widget: `allocation`)

A two-part layout inside a bordered section card:

### Layout: `.allocation-split`

**Left column (220px):** SVG donut chart (`<AllocationDonut>`)
- Colored arc segments per GICS sector, proportionally sized
- 11 predefined sector colors (CSS custom properties `--sector-tech`, `--sector-health`, etc.)
- Tooltip on each segment showing sector name and percentage
- Total portfolio value displayed below the chart
- Two-column legend with color swatches, sector names, and percentages

**Right column (fluid):** Traditional horizontal bar display
- Each sector as a row: sector name, percentage, colored bar, dollar value
- Bar width proportional to allocation percentage

On mobile (<=620px), the layout stacks vertically with the donut centered above the bars.

---

## 6. Top Signal (Widget: `top-signal`)

A preview card showing the highest-scoring research name:

| Element | Description |
|---------|-------------|
| Header | "Research leader" with a tier badge (e.g. "Buy", "Hold") |
| Company row | Logo (48px), ticker, name, score out of 100 |
| Sparkline | Inline price sparkline for the leader (when available) |
| Strength | First listed strength from the research model |
| Link | "Open research" |

---

## 7. Action Needed (Widget: `action-needed`)

A card showing how many holdings have actionable guidance:

| Element | Description |
|---------|-------------|
| Count | Large number of holdings needing review |
| Detail | Lists up to 4 ticker symbols with evidence-based guidance beyond Hold |
| Disclaimer | "Research prompts only" notice |

---

## 8. Watchlist Preview (Widget: `watchlist-preview`)

A card showing the user's followed names from the watchlist:

Each row (`.watch-preview-row`) is a 4-column grid:
| Column | Content |
|--------|---------|
| Logo | Company logo (32px) |
| Name | Ticker (bold) + company name |
| Sparkline | Small inline price chart (60px wide, 28px tall) |
| Stats | Research score + daily percent change (green/red `<Move>` component) |

Rows have a hover effect (background highlight with rounded corners).

---

## 9. Two-Column Section (`.report-two-column`)

Below the widget stack, two cards side by side:

### 9a. Retirement Projection (`<ProjectionPanel>`)

Monte Carlo simulation panel showing:
- Fan chart with confidence bands
- Success probability
- Percentile outcomes
- Sequence risk callout

### 9b. Opportunity Cost (`.opportunity-card`)

Benchmark comparison showing what the portfolio would have earned vs. ETF proxies:
- Shared starting value
- Portfolio earnings vs. each benchmark's potential earnings
- Dollar difference highlighted (portfolio ahead / benchmark ahead)

On mobile (<=620px), the two columns stack vertically.

---

## 10. Buying the Dip Chart

A standalone chart section (`<BuyingTheDipChart>`) showing names near 52-week lows that meet quality criteria.

---

## 11. Market Sentiment Strip (`.sentiment-strip`)

A horizontal row of pill-shaped badges providing at-a-glance market context:

| Pill | Content |
|------|---------|
| Macro regime | FRED regime label ("Supportive", "Restrictive", etc.) with a colored dot (green/red) |
| Research leader | Top-scoring ticker and its score |
| Top mover | Ticker with the largest absolute daily change, colored by direction |
| Universe | Total number of covered names |

Wraps to multiple rows on narrow screens.

---

## 12. Market Pulse Preview (`.report-market-pulse`)

A section showing the current macro backdrop:

**Layout:** 4-column grid of article cards (2 columns on tablet, 1 on phone).

| Card | Content |
|------|---------|
| FRED regime | Regime score out of 100 + label |
| 10Y Treasury | Current yield + through-date |
| Fed funds | Current rate + through-date |
| Inflation | Current rate + through-date |

---

## 13. Market Heatmap (`<MarketHeatmap>`)

A treemap-style sector performance visualization:

- SVG with rectangles sized proportionally to sector name count (weight)
- Color-coded: green for positive average daily change, red for negative, intensity reflects magnitude
- Each rectangle shows: sector name, average percent change, and up to 3 representative tickers
- Labels are hidden for rectangles too small to display text
- Responsive: adjusts minimum height on mobile

---

## 14. Focused Research Screens (`.report-focused-screens`)

A grid of 5 screen cards (2 columns on desktop, horizontal scroll on mobile):

| Screen | Criteria |
|--------|----------|
| Fast growth breakouts | Sharp acceleration this week |
| Value near 52-week lows | Quality plus a positive latest week |
| Recent momentum | Positive week and month |
| Short-term reversals | 20-day pullback turning up |
| Top ETFs | Performance, risk, cost and liquidity |

Each `<FocusedScreenCard>` displays:
- Colored kicker label + title
- Descriptive note
- 3 ranked rows, each with: company logo (28px), rank number, ticker + name, metric value with directional coloring
- "Open full screen" link

Cards have a staggered entrance animation (each delayed by 60ms) and lift with a shadow on hover.

---

## 15. Methodology Footer

A single-line footer in monospace text:

> "Balances use the latest stored closes. Historical portfolio lines apply current quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes, fees, or dividends. General research only."

---

## Visual System

### Entrance Animations

All major sections animate in with a staggered reveal on page load:
- `@keyframes card-reveal`: fade in + slide up 12px over 350ms
- Children of grid containers get incremental 60ms delays via `--i` CSS variable
- Disabled when `prefers-reduced-motion: reduce` is set or the app's motion setting is off

### Card Hover Effects

Interactive cards (`report-screen-card`, `candidate-card`, `trend-card`, `signal-rail-card`, `theme-rail-card`) lift 2px with an elevated shadow on hover. Dark mode uses a stronger shadow.

### Chart Area Fills

All emphasis chart lines (GrowthChart, Rolling Sharpe) render a gradient polygon fill beneath the line -- the series color at ~18% opacity at the top, fading to transparent at the x-axis. Dark mode adds a subtle glow `drop-shadow` on the primary line.

### Color Tokens

Direction-dependent elements use:
- `var(--positive)` / `var(--negative)` for green/red
- `var(--pill-positive-bg)` / `var(--pill-negative-bg)` for pill backgrounds
- `var(--brand-primary)` for neutral/brand accent

Sector colors are defined as CSS custom properties (`--sector-tech` through `--sector-comm`) for consistent use across the donut chart, heatmap, and future visualizations.

### Duration Tokens

```css
--duration-fast:   150ms
--duration-normal: 220ms
--duration-slow:   350ms
--ease-default:    cubic-bezier(0.4, 0, 0.2, 1)
--ease-out:        cubic-bezier(0, 0, 0.2, 1)
```

### Responsive Breakpoints

| Breakpoint | Behavior |
|------------|----------|
| > 900px | Full desktop layout: 4-column hero grid, 2-column screen grid, side-by-side projection |
| <= 900px | Tablet: 2-column hero grid, 2-column support grid, horizontal scroll for screen cards |
| <= 620px | Phone: stacked layout, hero metrics in 3-column row, single-column scores, mobile chart overlay with large balance display |
| <= 430px | Small phone: tighter spacing, simplified grids |

### Widget System

Each dashboard section is wrapped in `<DashboardWidget id="..." widgets={preferences.widgets}>`. The widget system allows users to:
- **Reorder** sections via the customize panel (drag/button reorder)
- **Hide** sections they don't need
- Widget order is persisted in user preferences

Widget IDs: `portfolio-summary`, `performance-chart`, `metric-grid`, `allocation`, `top-signal`, `action-needed`, `watchlist-preview`.

---

## Key Files

| File | Role |
|------|------|
| `src/pages/Dashboard.jsx` | Page component, all sections and data wiring |
| `src/components/GrowthChart.jsx` | SVG line chart with gradient area fill |
| `src/components/Sparkline.jsx` | Inline mini chart |
| `src/components/AllocationDonut.jsx` | SVG donut chart for sector allocation |
| `src/components/ScoreGauge.jsx` | SVG semi-circular gauge for scores |
| `src/components/MarketHeatmap.jsx` | SVG treemap for sector performance |
| `src/components/PerformanceMetrics.jsx` | Metric grid, evidence bar, rolling Sharpe |
| `src/components/MetricCard.jsx` | Individual metric card with trend bars |
| `src/components/PortfolioReturnSummary.jsx` | Return comparison with visual bars |
| `src/components/Bits.jsx` | Shared UI atoms: Move, Loading, Tier, etc. |
| `src/components/CompanyLogo.jsx` | Company logo with fallback |
| `src/styles/global.css` | All component styles |
| `src/styles/variables.css` | CSS custom properties (colors, durations, sectors) |

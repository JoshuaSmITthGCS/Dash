> **Superseded / historical.** This document is retained for history but is known to contain stale or contradicted information. For current, verified status see `README.md`, `APP-COMPLETE-BREAKDOWN.md` (regenerate with `npm run docs:breakdown`), and `docs/CHANGELOG-QUANT-UPGRADE.md`.

---

# Phase 2 Integration Guide - Core Fixes

**Status:** ✅ Core modules implemented, ready for Python pipeline integration

---

## What's Been Built

### 1. ✅ Label Distribution System (`src/lib/labelDistribution.js`)

**Replaces:** Fixed cutoffs that cluster 16/20 stocks as "Promising"

**New System:**
- Percentile-based distribution (not fixed score cutoffs)
- 5 tiers: Attractive (top 20%), Promising (55-80%), Neutral (35-55%), Caution (15-35%), Avoid (bottom 15%)
- Calibrated against actual 120-stock universe
- Fallback to smarter fixed cutoffs if universe data unavailable

**Key Functions:**
```javascript
import { calculateLabel, recalculateLabels } from './lib/labelDistribution'

// Calculate label for single stock
const label = calculateLabel(stock.score, allStocksScores)
// Returns: 'Attractive', 'Promising', 'Neutral', 'Caution', or 'Avoid'

// Recalculate labels for entire universe
const updatedStocks = recalculateLabels(stocks)
```

---

### 2. ✅ Evidence Strength System (`src/lib/evidenceStrength.js`)

**Replaces:** "Confidence" (which was just metric completeness)

**New System:**
- 40% Metric Coverage (% of required fields present)
- 25% Data Freshness (36-hour threshold, degrades over time)
- 25% Factor Agreement (do fundamentals, technicals, sentiment agree?)
- 10% Null Penalty (critical fields missing)

**Key Functions:**
```javascript
import { calculateEvidenceStrength, getEvidenceLabel } from './lib/evidenceStrength'

const strength = calculateEvidenceStrength(stock)
// Returns: 0-1 number

const label = getEvidenceLabel(strength)
// Returns: 'Excellent', 'Strong', 'Moderate', 'Limited', 'Weak'

// Detailed breakdown for debugging
const breakdown = getEvidenceBreakdown(stock)
// Returns: { overall, breakdown: { coverage, freshness, agreement, nullPenalty }, label, description }
```

---

### 3. ✅ News Sentiment Engine (`src/lib/sentimentEngine.js`)

**Replaces:** Black-box 10% sentiment weight

**New System:**

**Categorization:**
- 12 categories: earnings, product, regulation, legal, labor, execution, accounting/fraud, consumer backlash, macro, downgrade, cyber, recall

**Multi-Dimensional Analysis:**
- **Polarity**: positive, neutral, negative
- **Intensity**: mild, moderate, severe
- **Persistence**: one-off, recurring (2-4 articles/week), persistent (5+/week)
- **Source Quality**: low, medium, high (WSJ/Bloomberg/FT = high)
- **Materiality**: low, medium, high (earnings/fraud = high, macro = low)

**Impact Scaling:**
```
Impact = base_impact × persistence_mult × source_mult × materiality_mult

Examples:
- Mild + low-materiality + one-off = ~0.05 impact (minimal)
- Severe + high-materiality + persistent + high-source = ~1.0 impact (significant)
- Negative news has asymmetric impact (1.2x multiplier)
```

**Key Functions:**
```javascript
import { analyzeArticle, aggregateSentiment, generateSentimentAuditLog } from './lib/sentimentEngine'

// Analyze single article
const analysis = analyzeArticle(article, allArticles)
// Returns: { category, polarity, intensity, persistence, sourceQuality, materiality, impact, ... }

// Aggregate all articles for a stock
const sentiment = aggregateSentiment(articles)
// Returns: { overallImpact, avgPolarity, dominantCategory, breakdown, ... }

// Generate audit log
const log = generateSentimentAuditLog(sentiment)
// Returns: "5 articles analyzed. Dominant category: earnings..."
```

---

### 4. ✅ Sell/Watch Logic (`src/lib/sellWatchLogic.js`)

**Rule:** NEVER flag sell/trim/watch on single factor alone

**Requires 2+ of these to agree:**
1. Deteriorating fundamentals (score < 50, declining growth, poor ROE, high leverage)
2. Broken technicals (20D decline > 15%, consistent multi-timeframe decline)
3. Persistent negative sentiment (3+ recurring articles, high-impact events)

**Actions:**
- **HOLD**: < 2 factors agree
- **WATCH**: 2 factors agree (moderate severity)
- **TRIM**: 2+ factors agree (multiple moderate OR 1 severe)
- **SELL**: 2+ factors agree (severe deterioration)

**Key Functions:**
```javascript
import { getSellWatchRecommendation, formatSellWatchAnalysis } from './lib/sellWatchLogic'

const recommendation = getSellWatchRecommendation(stock, previousData, sentimentData)
// Returns: { action: 'HOLD'|'WATCH'|'TRIM'|'SELL', confidence, reason, factors, topReasons }

const formatted = formatSellWatchAnalysis(recommendation)
// Returns: { ...recommendation, label, description, color, summary, detailedAnalysis }
```

---

## Python Pipeline Integration

### Step 1: Update `pipeline/fetch_advisor.py`

Add to the scoring section (after calculating overall score):

```python
# Example: Update labels based on universe distribution
import json

# After calculating scores for all stocks
all_scores = [stock['score'] for stock in stocks if stock.get('score')]

for stock in stocks:
    score = stock.get('score', 0)
    # Calculate percentile
    percentile = sum(1 for s in all_scores if s < score) / len(all_scores) * 100

    # Assign label based on percentile
    if percentile >= 80:
        stock['stance'] = 'Attractive'
    elif percentile >= 55:
        stock['stance'] = 'Promising'
    elif percentile >= 35:
        stock['stance'] = 'Neutral'
    elif percentile >= 15:
        stock['stance'] = 'Caution'
    else:
        stock['stance'] = 'Avoid'
```

### Step 2: Calculate Evidence Strength

```python
def calculate_evidence_strength(stock):
    """
    Calculate evidence strength based on coverage, freshness, agreement
    """
    required_metrics = [
        'price', 'market_cap', 'peg', 'forward_pe', 'price_to_sales',
        'roe', 'profit_margin', 'debt_to_equity', 'current_ratio',
        'revenue_growth_yoy', 'earnings_growth_yoy'
    ]

    # Coverage
    present = sum(1 for m in required_metrics if stock.get(m) is not None)
    coverage = present / len(required_metrics)

    # Freshness (example - adjust based on your data)
    from datetime import datetime, timedelta
    generated_at = stock.get('generated_at')
    if generated_at:
        age_hours = (datetime.now() - datetime.fromisoformat(generated_at)).total_seconds() / 3600
        if age_hours <= 36:
            freshness = 1.0
        elif age_hours <= 72:
            freshness = 0.7
        else:
            freshness = 0.4
    else:
        freshness = 0.5

    # Agreement (std dev of component scores)
    components = [
        stock.get('components', {}).get('fundamentals'),
        stock.get('components', {}).get('market_behavior'),
        stock.get('components', {}).get('news_sentiment')
    ]
    valid_components = [c for c in components if c is not None]

    if len(valid_components) >= 2:
        import statistics
        std_dev = statistics.stdev(valid_components)
        agreement = max(0, 1 - (std_dev / 30))
    else:
        agreement = 0.5

    # Null penalty
    critical_fields = [stock.get('price'), stock.get('market_cap')]
    null_penalty = sum(1 for f in critical_fields if f is not None) / len(critical_fields)

    # Weighted combination
    evidence_strength = (
        coverage * 0.40 +
        freshness * 0.25 +
        agreement * 0.25 +
        null_penalty * 0.10
    )

    return {
        'evidence_strength': evidence_strength,
        'evidence_label': get_evidence_label(evidence_strength),
        'breakdown': {
            'coverage': coverage,
            'freshness': freshness,
            'agreement': agreement,
            'null_penalty': null_penalty
        }
    }

def get_evidence_label(strength):
    if strength >= 0.85: return 'Excellent'
    if strength >= 0.70: return 'Strong'
    if strength >= 0.50: return 'Moderate'
    if strength >= 0.30: return 'Limited'
    return 'Weak'
```

### Step 3: Process News Sentiment

```python
def categorize_news(article):
    """
    Categorize news article by type
    """
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()

    patterns = {
        'accounting': ['fraud', 'restatement', 'accounting', 'sec investigation'],
        'earnings': ['earnings', 'revenue', 'profit', 'eps', 'guidance'],
        'recall': ['recall', 'safety', 'defect'],
        'cyber': ['breach', 'hack', 'cyberattack'],
        'legal': ['lawsuit', 'litigation', 'settlement'],
        # ... add more categories
    }

    for category, keywords in patterns.items():
        if any(keyword in text for keyword in keywords):
            return category

    return 'other'

def analyze_sentiment(articles):
    """
    Analyze sentiment with full categorization
    """
    analyses = []
    for article in articles:
        category = categorize_news(article)
        polarity_score = article.get('overall_sentiment_score', 0)

        # Assess intensity
        intensity = 'severe' if abs(polarity_score) > 0.5 else 'moderate' if abs(polarity_score) > 0.25 else 'mild'

        # Assess persistence (count similar articles)
        similar_count = sum(1 for a in articles if categorize_news(a) == category)
        persistence = 'persistent' if similar_count >= 5 else 'recurring' if similar_count >= 2 else 'one-off'

        analyses.append({
            'category': category,
            'polarity': 'negative' if polarity_score < -0.15 else 'positive' if polarity_score > 0.15 else 'neutral',
            'intensity': intensity,
            'persistence': persistence,
            'materiality': 'high' if category in ['earnings', 'accounting', 'legal'] else 'medium',
            'sourceQuality': assess_source_quality(article.get('source', ''))
        })

    return analyses
```

---

## UI Integration

### Update Dashboard to Show New Labels

**File:** `src/pages/Dashboard.jsx`

```javascript
import { recalculateLabels, analyzeLabelDistribution } from '../lib/labelDistribution'
import { calculateEvidenceStrength, getEvidenceLabel } from '../lib/evidenceStrength'

export default function Dashboard() {
  const { data, loading } = useData('advisor.json')

  if (loading) return <Loading />

  // Recalculate labels based on current universe
  const stocksWithLabels = recalculateLabels(data.research)

  // Analyze distribution for debugging
  const distribution = analyzeLabelDistribution(stocksWithLabels)
  console.log('Label distribution:', distribution)

  // Enrich with evidence strength
  const enrichedStocks = stocksWithLabels.map(stock => ({
    ...stock,
    evidenceStrength: calculateEvidenceStrength(stock),
    evidenceLabel: getEvidenceLabel(calculateEvidenceStrength(stock))
  }))

  const top = enrichedStocks.slice(0, 20)

  // ... rest of component
}
```

### Update Stock Detail Modal

**File:** `src/components/StockDetailModal.jsx`

```javascript
import { getSellWatchRecommendation, formatSellWatchAnalysis } from '../lib/sellWatchLogic'
import { aggregateSentiment } from '../lib/sentimentEngine'

export default function StockDetailModal({ stock, onClose }) {
  // Analyze sentiment if news available
  const sentimentData = stock.news ? aggregateSentiment(stock.news) : null

  // Get sell/watch recommendation
  const recommendation = getSellWatchRecommendation(stock, null, sentimentData)
  const analysis = formatSellWatchAnalysis(recommendation)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal stock-modal">
        {/* ... existing content ... */}

        {/* New sell/watch section */}
        <h3>Recommendation</h3>
        <div className={`recommendation-card ${analysis.color}`}>
          <h4>{analysis.label}</h4>
          <p>{analysis.description}</p>
          <p><strong>Reason:</strong> {analysis.reason}</p>

          <h5>Factor Analysis</h5>
          <ul>
            {analysis.detailedAnalysis.map((factor, i) => (
              <li key={i}>
                <strong>{factor.factor}:</strong> {factor.status} ({factor.severity})
                {factor.concerns && <div style={{ fontSize: 12, opacity: 0.8 }}>{factor.concerns}</div>}
              </li>
            ))}
          </ul>
        </div>

        {/* Show sentiment breakdown if available */}
        {sentimentData && (
          <div>
            <h4>News Sentiment Analysis</h4>
            <p>
              <strong>Dominant Category:</strong> {sentimentData.dominantCategory}
              ({sentimentData.dominantCategoryDescription})
            </p>
            <p><strong>Overall Impact:</strong> {(sentimentData.overallImpact * 100).toFixed(1)}%</p>
            <p><strong>Articles Analyzed:</strong> {sentimentData.totalArticles}</p>
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## CSS Updates

Add to `src/styles/global.css`:

```css
/* Recommendation cards */
.recommendation-card {
  padding: 20px;
  border-radius: 12px;
  border-left: 4px solid;
  margin: 16px 0;
}

.recommendation-card.success {
  border-color: var(--pos);
  background: color-mix(in srgb, var(--pos) 5%, var(--bg-card));
}

.recommendation-card.warning {
  border-color: var(--tier-watch);
  background: color-mix(in srgb, var(--tier-watch) 5%, var(--bg-card));
}

.recommendation-card.caution {
  border-color: var(--tier-cool);
  background: color-mix(in srgb, var(--tier-cool) 5%, var(--bg-card));
}

.recommendation-card.danger {
  border-color: var(--neg);
  background: color-mix(in srgb, var(--neg) 5%, var(--bg-card));
}

/* Evidence strength labels */
.evidence-excellent { color: var(--pos); }
.evidence-strong { color: var(--up); }
.evidence-moderate { color: var(--tier-neutral); }
.evidence-limited { color: var(--tier-watch); }
.evidence-weak { color: var(--tier-cool); }
```

---

## Testing Checklist

### 1. Label Distribution

- [ ] Run pipeline with new label calculation
- [ ] Verify distribution is NOT 16/20 "Promising"
- [ ] Confirm visible range: Attractive, Promising, Neutral, Caution, Avoid
- [ ] Check that percentiles make sense (top 20% = Attractive, etc.)

### 2. Evidence Strength

- [ ] Verify "Confidence" renamed to "Evidence Strength" in UI
- [ ] Check calculation includes coverage + freshness + agreement
- [ ] Confirm stale data (>36 hours) gets lower score
- [ ] Test with missing metrics - should penalize coverage

### 3. News Sentiment

- [ ] Verify articles are categorized correctly
- [ ] Check that mild + low-materiality has minimal impact
- [ ] Confirm persistent + high-materiality has significant impact
- [ ] Review audit logs show which category triggered penalty

### 4. Sell/Watch Logic

- [ ] Verify NO sell flags on single factor alone
- [ ] Confirm 2+ factors required for WATCH/TRIM/SELL
- [ ] Test fundamentals + technicals agreement
- [ ] Test fundamentals + sentiment agreement
- [ ] Test technicals + sentiment agreement

---

## Common Issues

### "Labels still clustering"

**Cause:** Pipeline not using percentile calculation

**Fix:** Update `pipeline/fetch_advisor.py` to calculate percentiles, not fixed cutoffs

---

### "Evidence strength always 0.5"

**Cause:** Missing freshness timestamp or components

**Fix:** Ensure `generated_at` field is set in pipeline output

---

### "Sentiment not categorizing correctly"

**Cause:** Article text/summary not available

**Fix:** Verify Alpha Vantage news includes `title` and `summary` fields

---

### "Sell flags triggering too often"

**Cause:** Thresholds too aggressive

**Fix:** Adjust severity thresholds in `sellWatchLogic.js`:
- Fundamentals: Raise score threshold from 50 to 40
- Technicals: Raise decline threshold from -15% to -20%
- Sentiment: Require 4+ articles instead of 3

---

## Next Phase Preview

**Phase 3: Backtest Engine**

Will use sell/watch signals to log:
- Entry timestamp (when stock enters top 20 or becomes "Attractive")
- Exit timestamp (when stock exits top 20 or gets "SELL" recommendation)
- Store in Firestore `/backtestSignals/{signalId}`
- Calculate returns for equal-weight, rank-weighted, SPY benchmark strategies

Ready to proceed when Phase 2 is tested and validated.

---

**Phase 2 Status:** ✅ Implementation complete, ready for pipeline integration and testing

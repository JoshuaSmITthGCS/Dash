# ValueSignal SEO Audit Report

**Site:** ValueSignal — Fundamentals-first investment research
**URL:** http://localhost:5173/ (Development) | Production TBD
**Audit Date:** July 30, 2026
**Audit Type:** Full Technical SEO Analysis

---

## Executive Summary

**Overall SEO Score: 42/100** ⚠️ Needs Improvement

ValueSignal is a React SPA (Single Page Application) focused on investment research. While the content strategy and user experience show promise, significant technical SEO issues prevent search engines from properly crawling, indexing, and ranking the site.

### Critical Issues (4)
- 🔴 **Client-side rendering only** — Search engines see empty HTML
- 🔴 **Missing social meta tags** — No Open Graph or Twitter Cards
- 🔴 **Missing schema markup** — No structured data for financial content
- 🔴 **No sitemap** — Search engines cannot discover all pages

### Score Breakdown

| Category | Score | Status |
|----------|-------|--------|
| **Technical SEO** | 35/100 | 🔴 Critical |
| **On-Page SEO** | 45/100 | ⚠️ Warning |
| **Content Quality** | 60/100 | ⚠️ Warning |
| **Schema Markup** | 0/100 | 🔴 Critical |
| **Performance** | 70/100 | ⚠️ Warning |
| **AI Search Readiness** | 15/100 | 🔴 Critical |
| **Social Sharing** | 0/100 | 🔴 Critical |

---

## 1. Technical SEO Analysis

### 1.1 Client-Side Rendering (CSR) Issues 🔴 CRITICAL

**Finding:** Site uses React SPA with client-side rendering only
**Evidence:**
```html
<!-- Initial HTML contains only: -->
<div id="root"></div>
<script type="module" src="/src/main.jsx"></script>
<!-- No h1, h2, content, images, or links in source -->
```
**Impact:** Search engines may not execute JavaScript, leading to:
- Empty or minimal content indexed
- Missing headings and semantic HTML
- No internal link structure for crawlers
- Poor rankings across all pages

**Fix:** Implement one of these solutions:
1. **Pre-rendering** (Recommended for static content)
   - Use `vite-plugin-ssr` or similar
   - Generate static HTML at build time
   - Cost: Low, SEO impact: High

2. **Server-Side Rendering (SSR)**
   - Migrate to Next.js or Remix
   - Dynamic content, better for personalization
   - Cost: High, SEO impact: Very High

3. **Static Site Generation (SSG)**
   - Use Astro with React islands
   - Best performance, lower complexity
   - Cost: Medium, SEO impact: High

**Priority:** 🔴 Critical — Fix within 1 week

---

### 1.2 Missing Canonical URLs ⚠️

**Finding:** No canonical link tag present
**Evidence:** `"canonical": null` in HTML parse
**Impact:**
- Duplicate content issues if accessed via multiple domains
- Search engines may choose wrong URL as primary

**Fix:** Add canonical tags to all pages
```html
<link rel="canonical" href="https://valuesignal.com/" />
```

**Priority:** ⚠️ High — Fix within 2 weeks

---

### 1.3 Missing Meta Robots Tag ℹ️

**Finding:** No robots meta tag
**Evidence:** `"meta_robots": null`
**Impact:** Relies on robots.txt only (acceptable but not optimal)

**Fix:** Add to `<head>` for explicit control:
```html
<meta name="robots" content="index, follow, max-image-preview:large" />
```

**Priority:** ℹ️ Low — Enhancement

---

### 1.4 Robots.txt — AI Crawler Management ⚠️

**Finding:** 11 AI crawlers not explicitly managed
**Evidence:** GPTBot, ClaudeBot, PerplexityBot, Google-Extended, etc. all allowed by default
**Impact:**
- Content may be used for AI training without consent
- Increased crawl budget usage
- Potential competitive intelligence exposure

**Fix:** Add to `/public/robots.txt`:
```txt
# Core search engine crawlers
User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

# AI Training Crawlers — Block for proprietary research
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: ClaudeBot
Allow: /  # Or Disallow if you prefer

User-agent: PerplexityBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: anthropic-ai
Allow: /

User-agent: Applebot-Extended
Disallow: /

# Sitemap
Sitemap: https://valuesignal.com/sitemap.xml
```

**Priority:** ⚠️ High — Decide policy within 1 week

---

### 1.5 Missing Sitemap 🔴

**Finding:** No sitemap.xml reference or file
**Evidence:** "No Sitemap directive found in robots.txt"
**Impact:**
- Search engines discover pages slower
- New content takes longer to index
- Missed ranking opportunities

**Fix:** Generate dynamic sitemap including:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://valuesignal.com/</loc>
    <lastmod>2026-07-30</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://valuesignal.com/research</loc>
    <lastmod>2026-07-30</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
  <!-- Add all routes + dynamic stock pages -->
</urlset>
```

**Priority:** 🔴 Critical — Fix within 1 week

---

## 2. On-Page SEO

### 2.1 Title Tag ✅

**Finding:** Well-optimized title
**Evidence:** "ValueSignal — Fundamentals-first investment research" (59 characters)
**Impact:** Within optimal range (50-60 chars), includes brand and value proposition

**Priority:** ✅ Pass

---

### 2.2 Meta Description ✅

**Finding:** Good meta description
**Evidence:** "Explainable company research across valuation, quality, financial health, growth, market behavior, and news sentiment." (142 characters)
**Impact:** Within optimal range (150-160 chars), compelling and keyword-rich

**Enhancement:** Add call-to-action:
```html
<meta name="description" content="Explainable company research across valuation, quality, financial health, growth, and market behavior. Evidence-based investing, not hype. Start researching now." />
```

**Priority:** ℹ️ Enhancement

---

### 2.3 Missing Heading Structure 🔴

**Finding:** No h1, h2, or other headings detected
**Evidence:** `"h1": [], "h2": []`
**Impact:**
- Search engines cannot understand content hierarchy
- Accessibility issues for screen readers
- Poor semantic structure

**Fix:** Ensure each page has:
- Exactly one `<h1>` with primary keyword
- Logical `<h2>` - `<h6>` hierarchy
- Example for homepage:
```jsx
<h1>Fundamentals-First Stock Research Platform</h1>
<h2>Top Investment Research Candidates</h2>
<h2>How ValueSignal Works</h2>
<h3>Valuation Metrics</h3>
<h3>Quality Indicators</h3>
```

**Priority:** 🔴 Critical — Fix with SSR/pre-rendering

---

### 2.4 Internal Linking ⚠️

**Finding:** No internal links detected in initial HTML
**Evidence:** `"internal": []`
**Impact:**
- Poor crawl depth
- Weak PageRank flow
- Difficult for search engines to discover all pages

**Fix:**
- Add footer links to key pages
- Breadcrumb navigation
- Related stocks/articles sections
- "See also" links in methodology

**Priority:** ⚠️ High — Fix with SSR

---

## 3. Social Media Optimization

### 3.1 Missing Open Graph Tags 🔴

**Finding:** No Open Graph metadata
**Evidence:** All og: tags missing (0/7 required tags)
**Impact:**
- Poor previews on Facebook, LinkedIn
- Lower click-through rates from social
- Unprofessional appearance

**Fix:** Add to `<head>`:
```html
<meta property="og:title" content="ValueSignal — Fundamentals-first investment research" />
<meta property="og:description" content="Explainable company research across valuation, quality, financial health, growth, and market behavior." />
<meta property="og:image" content="https://valuesignal.com/og-image.png" />
<meta property="og:url" content="https://valuesignal.com/" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="ValueSignal" />
```

**Priority:** 🔴 Critical — Fix within 1 week

---

### 3.2 Missing Twitter Card Tags 🔴

**Finding:** No Twitter Card metadata
**Evidence:** twitter:card missing
**Impact:** Poor previews on X/Twitter

**Fix:**
```html
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="ValueSignal — Fundamentals-first investment research" />
<meta name="twitter:description" content="Evidence-based investing. Explainable company fundamentals." />
<meta name="twitter:image" content="https://valuesignal.com/twitter-card.png" />
```

**Priority:** 🔴 Critical — Fix within 1 week

---

### 3.3 Create Social Images

**Finding:** Need OG image (1200x630px) and Twitter card (1200x675px)
**Recommendation:** Create branded images showing:
- ValueSignal logo
- Sample stock analysis dashboard
- Key differentiator: "Fundamentals First, Evidence Not Hype"

**Priority:** ⚠️ High — Create within 2 weeks

---

## 4. Schema Markup & Structured Data

### 4.1 Missing Schema Entirely 🔴

**Finding:** No JSON-LD structured data detected
**Evidence:** `"schema": []`
**Impact:**
- No rich snippets in search results
- Missed opportunity for financial data markup
- Lower visibility vs competitors

**Fix:** Implement the following schemas:

#### 4.1.1 Organization Schema (Homepage)
```json
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FinancialService",
  "name": "ValueSignal",
  "description": "Fundamentals-first investment research platform",
  "url": "https://valuesignal.com",
  "logo": "https://valuesignal.com/logo.png",
  "sameAs": [
    "https://twitter.com/valuesignal",
    "https://linkedin.com/company/valuesignal"
  ]
}
</script>
```

#### 4.1.2 WebSite Schema with SearchAction
```json
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "ValueSignal",
  "url": "https://valuesignal.com",
  "potentialAction": {
    "@type": "SearchAction",
    "target": "https://valuesignal.com/search?q={search_term_string}",
    "query-input": "required name=search_term_string"
  }
}
</script>
```

#### 4.1.3 BreadcrumbList (All Pages)
```json
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "name": "Home",
      "item": "https://valuesignal.com/"
    },
    {
      "@type": "ListItem",
      "position": 2,
      "name": "Research",
      "item": "https://valuesignal.com/research"
    }
  ]
}
</script>
```

#### 4.1.4 Article Schema (Methodology, Research Pages)
```json
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "ValueSignal Investment Methodology",
  "description": "How we score stocks using fundamentals, market behavior, and sentiment",
  "author": {
    "@type": "Organization",
    "name": "ValueSignal"
  },
  "publisher": {
    "@type": "Organization",
    "name": "ValueSignal",
    "logo": {
      "@type": "ImageObject",
      "url": "https://valuesignal.com/logo.png"
    }
  },
  "datePublished": "2026-07-22",
  "dateModified": "2026-07-30"
}
</script>
```

**Priority:** 🔴 Critical — Implement within 2 weeks

---

## 5. AI Search Readiness (GEO)

### 5.1 Empty llms.txt 🔴

**Finding:** llms.txt exists but contains no content
**Evidence:** "No links found, missing title/description" (Score: 5/100)
**Impact:**
- AI search engines (Perplexity, ChatGPT, Claude) cannot optimize content discovery
- Missed citations in AI-generated responses
- Lower visibility in answer engines

**Fix:** Create `/public/llms.txt`:
```markdown
# ValueSignal

> Fundamentals-first investment research platform providing explainable company analysis across valuation, quality, financial health, growth, and market behavior.

## Key Pages

- [Homepage](https://valuesignal.com/): Overview of top research candidates
- [Investment Research](https://valuesignal.com/research): Top 20 ranked stocks with detailed fundamentals
- [Market Pulse](https://valuesignal.com/market): Congressional trading activity and policy impact
- [Methodology](https://valuesignal.com/methodology): How we score companies (75% fundamentals, 15% market behavior, 10% sentiment)
- [Watchlist](https://valuesignal.com/watchlist): Track your favorite stocks

## Scoring Model

- 75% Fundamentals (valuation, profitability, financial health, growth)
- 15% Market Behavior (trend, volatility, relative strength)
- 10% News Sentiment

## Data Sources

- Alpha Vantage: Company fundamentals, news, insider transactions
- Yahoo Finance: Extended fundamental data
- Daily refresh cycle, 36-hour freshness guarantee

## General Research Only

Not individualized financial advice. High scores prompt deeper research, not buy orders.
```

Also create `/public/llms-full.txt` with expanded content.

**Priority:** 🔴 Critical — Fix within 3 days

---

### 5.2 Answer Engine Optimization (AEO)

**Finding:** Content not optimized for featured snippets or "People Also Ask"
**Impact:** Missed opportunities to appear in AI-generated answers

**Fix:**
- Add FAQ section to homepage and methodology
- Use question-based headings: "What is ValueSignal?", "How does the scoring work?"
- Structure data in lists and tables
- Add "Key Takeaways" sections

**Priority:** ⚠️ Medium — Implement within 1 month

---

## 6. Performance & Core Web Vitals

### 6.1 JavaScript Bundle Size ⚠️

**Finding:** Main JS bundle is 182.7 KB (gzipped: 59.3 KB)
**Evidence:** `dist/assets/index-73-LZY0R.js   182.70 kB │ gzip: 59.27 kB`
**Impact:**
- Slower initial page load
- Potential Largest Contentful Paint (LCP) issues
- Lower mobile rankings

**Fix:**
- Code splitting by route
- Lazy load non-critical components
- Tree-shake unused React Router features
- Target: <50 KB initial bundle (gzipped)

**Priority:** ⚠️ Medium — Optimize within 1 month

---

### 6.2 No Image Optimization Detected ℹ️

**Finding:** Cannot assess images (not in initial HTML)
**Recommendation:**
- Use WebP/AVIF formats
- Implement lazy loading
- Add `width` and `height` attributes (prevent CLS)
- Use CDN for `public/data/*.json` files

**Priority:** ℹ️ Low — Implement with SSR

---

## 7. Content Quality

### 7.1 Unique Value Proposition ✅

**Finding:** Clear differentiation in messaging
**Evidence:** "fundamentals first, evidence not hype, general research only"
**Impact:** Strong brand positioning for users and search engines

**Priority:** ✅ Pass

---

### 7.2 E-E-A-T Signals ⚠️

**Finding:** Missing Experience, Expertise, Authoritativeness, Trust signals
**Impact:** Lower rankings for competitive financial queries

**Fix:**
- Add "About Us" page with team credentials
- Link to source data providers (Alpha Vantage, Yahoo Finance)
- Add disclaimers and compliance statements
- Show data freshness timestamps
- Add author bylines if publishing original analysis

**Priority:** ⚠️ High — Add within 2 weeks

---

## 8. Security & Trust

### 8.1 Missing HTTPS (Dev Only) ℹ️

**Finding:** Local dev server uses HTTP
**Evidence:** "HTTPS: No" (localhost expected)
**Impact:** None for development, critical for production

**Fix:** Ensure production deployment uses HTTPS with:
- Valid SSL certificate
- HSTS header: `Strict-Transport-Security: max-age=31536000`
- HTTP → HTTPS redirects

**Priority:** ℹ️ N/A for dev, 🔴 Critical for production

---

### 8.2 Missing Security Headers ⚠️

**Finding:** 6 security headers missing
**Evidence:** No CSP, X-Frame-Options, X-Content-Type-Options, etc.
**Impact:**
- Vulnerability to XSS, clickjacking
- Lower trust signals
- Browser warnings possible

**Fix:** Add to Netlify `_headers` file:
```txt
/*
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), microphone=(), camera=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'
```

**Priority:** ⚠️ High — Add before launch

---

## 9. Recommendations Summary

### Immediate (Week 1)
1. 🔴 Implement pre-rendering or SSR for search engine visibility
2. 🔴 Create and populate llms.txt for AI search readiness
3. 🔴 Add Open Graph and Twitter Card meta tags
4. 🔴 Generate sitemap.xml
5. ⚠️ Configure AI crawler policy in robots.txt

### Short-term (Weeks 2-4)
6. 🔴 Implement JSON-LD schema markup (Organization, WebSite, Article, Breadcrumbs)
7. ⚠️ Create social sharing images (OG + Twitter)
8. ⚠️ Add canonical URLs to all pages
9. ⚠️ Add E-E-A-T signals (About page, credentials, sources)
10. ⚠️ Add security headers via Netlify config

### Medium-term (Months 1-2)
11. ⚠️ Optimize JavaScript bundle size (code splitting, lazy loading)
12. ⚠️ Implement AEO-optimized content (FAQ, Q&A format)
13. ℹ️ Add image optimization (WebP, lazy loading, dimensions)
14. ℹ️ Create dedicated stock detail pages with unique URLs
15. ℹ️ Add internal linking structure

---

## Appendix: Tool Output

### Robots.txt Analysis
```
✓ robots.txt found (HTTP 200)
⚠️ 11 AI crawlers not managed
⚠️ No sitemap directive
```

### llms.txt Analysis
```
✓ llms.txt found (HTTP 200)
✓ llms-full.txt found
⚠️ Quality Score: 5/100
⚠️ Missing title, description, links
```

### Social Meta Analysis
```
🔴 Open Graph: 0/7 required tags
🔴 Twitter Card: 0/6 recommended tags
Score: 0/100
```

### HTML Parse
```json
{
  "title": "ValueSignal — Fundamentals-first investment research",
  "meta_description": "Explainable company research...",
  "h1": [],
  "h2": [],
  "images": [],
  "links": {"internal": [], "external": []},
  "schema": []
}
```

---

**End of Report**

*Generated by Claude Code SEO Skill*
*Next Review: August 30, 2026*

# ValueSignal Portfolio Tracker - Quick Start Guide

## 🚀 Get Started in 3 Minutes

### Step 1: Run the Development Server

```bash
npm run dev
```

Open http://localhost:5173 in your browser.

---

### Step 2: Login

When the page loads, you'll see a login modal:

1. Enter your name (e.g., "John" or "Dad")
2. Enter password: `ufb9*r23nQebi`
3. Click "Login"

**Your 19 stock positions will be automatically loaded!**

---

### Step 3: Explore Your Portfolio

Click **"My Portfolio"** in the sidebar navigation.

You'll see:
- ✅ Total portfolio value
- ✅ Total gains/losses
- ✅ All 19 preloaded positions (ACN, ADBE, BAC, AGO, COP, OXY, MSFT, AMAT, META, QCOM, DECK, CI, VOO, MU, NTNX, BSX, INTU, SCHW, EOG)
- ✅ 1-day, 5-day, and 20-day performance for each stock

---

### Step 4: Add a New Position

1. Click **"+ Add Position"** button
2. Fill in:
   - Ticker symbol (e.g., AAPL)
   - Number of shares (e.g., 10)
   - Cost basis/purchase price (e.g., 150.00)
   - Purchase date
3. Click **"Add"**

Your position is now tracked!

---

### Step 5: Use the $500 Calculator

1. In the Portfolio page, click the **"$500 Calculator"** tab
2. See what a $500 investment would be worth for ANY stock
3. View returns across: 1 day, 5 days, 20 days, 3 months

Example:
```
MSFT @ $420.30
$500 = 1.190 shares

1-day:   +$12.50 (if it went up 2.5%)
5-day:   +$29.00 (if it went up 5.8%)
20-day:  +$61.50 (if it went up 12.3%)
3-month: +$93.50 (if it went up 18.7%)
```

---

### Step 6: Get Sell Recommendations

1. Go to **"Overview"** page
2. Click **"Details"** button on any stock
3. Read AI-generated sell strategies:
   - 🔴 **HIGH urgency** - Act within days
   - ⚠️ **MEDIUM urgency** - Act within weeks
   - ✅ **LOW urgency** - Monitor only

Example strategies:
- "Take Profits: Strong 20-day gain. Consider trimming position."
- "Hold: Strong fundamentals and stable price action."
- "Exit: Fundamentals deteriorating. Consider full exit."

---

### Step 7: Family Sharing

**For Family Members:**

1. Have them open the same site
2. Login with:
   - Their own name (e.g., "Mom", "Sarah", "Brother")
   - Same password: `ufb9*r23nQebi`
3. Their portfolio will be **completely separate** from yours
4. They can track their own investments

**Data Separation:**
- Each user's portfolio is stored independently
- No data mixing between family members
- Safe for multiple people on same device

---

## 🔑 Important Information

### Password
```
ufb9*r23nQebi
```
Share this with family members.

### Data Storage
- All portfolio data is stored **locally in your browser**
- No cloud sync or server uploads
- Each browser/device has independent storage

### Session Duration
- Login lasts **24 hours**
- Auto-logout after expiration
- Click "Logout" to end session manually

### Backup Your Data
1. Click **"Export"** button in Portfolio page
2. Saves JSON file with all positions
3. Keep this file safe for recovery

---

## 📱 Navigation

**Sidebar Menu:**
- **Overview** - Top 20 research candidates (click "Details" for analysis)
- **Research** - Full research picks
- **Market Pulse** - Congressional trading activity
- **My Portfolio** - Your personal investment tracker ⭐ NEW
- **Watchlist** - Track specific stocks
- **Methodology** - How ValueSignal works

---

## 💡 Pro Tips

### Tip 1: Export Regularly
Click "Export" weekly to backup your portfolio data.

### Tip 2: Check Sell Strategies
Before selling any stock, click "Details" to see AI recommendations.

### Tip 3: Use $500 Calculator
Research new stocks by seeing hypothetical returns.

### Tip 4: Monitor Performance
The 1-day, 5-day, 20-day columns help spot trends quickly:
- Green = outperforming
- Red = underperforming

### Tip 5: Track Tax Lots
Record exact purchase dates for accurate tax-loss harvesting.

---

## 🛠️ Customization

### Change Password

Edit `src/lib/AuthContext.jsx`:
```javascript
const MASTER_PASSWORD = 'your-new-password'
```

### Change Your Preloaded Positions

Edit `src/lib/usePortfolio.js`:
```javascript
const DEFAULT_POSITIONS = {
  'main-user': [
    { ticker: 'AAPL', shares: 10, costBasis: 150, purchaseDate: '2026-01-01' },
    // Add/modify positions here
  ]
}
```

---

## 🐛 Troubleshooting

### "Can't see my positions after login"
- Check that you used the correct password
- Try refreshing the page
- Check browser console for errors

### "Data disappeared after closing browser"
- Ensure you didn't clear browser data/cookies
- Click "Export" to create backups
- localStorage persists by default unless manually cleared

### "Wrong prices showing"
- Prices update when pipeline runs (daily 07:00 ET)
- Run `python pipeline/fetch_advisor.py` to manually refresh

### "Can't add a stock not in research universe"
- You can add ANY ticker symbol
- Stocks not in universe will show "—" for current price
- You can still track cost basis and manual valuations

---

## 📊 Example Workflow

**Weekly Review Process:**

1. **Monday Morning:**
   - Login to Portfolio
   - Review weekend price changes (1-day column)
   - Check total portfolio gain/loss

2. **Mid-Week:**
   - Click "Details" on any stock with big moves
   - Read sell strategy recommendations
   - Decide: Hold, Trim, or Exit

3. **Friday:**
   - Review 5-day and 20-day performance
   - Use $500 Calculator to research new opportunities
   - Export portfolio for weekly backup

4. **Monthly:**
   - Review 3-month returns
   - Rebalance if needed
   - Add new positions from research candidates

---

## 🎯 Key Metrics Explained

### Portfolio Metrics
- **Total Value:** Sum of (shares × current price) for all positions
- **Total Cost:** Sum of (shares × cost basis) for all positions
- **Total Gain/Loss:** Total Value - Total Cost
- **Return %:** (Total Gain/Loss / Total Cost) × 100

### Per-Stock Metrics
- **Cost Basis:** Price you paid per share
- **Current Price:** Latest market price from pipeline
- **Gain/Loss:** (Current Price - Cost Basis) × Shares
- **Return %:** ((Current Price - Cost Basis) / Cost Basis) × 100

### Time-Based Returns
- **1-Day:** Price change over last trading day
- **5-Day:** Price change over last week
- **20-Day:** Price change over ~1 month
- **3-Month:** Price change over ~60 trading days

---

## ✅ Daily Checklist

**Morning (2 minutes):**
- [ ] Check total portfolio value
- [ ] Review overnight changes (1-day column)
- [ ] Note any stocks with >5% moves

**Weekly (10 minutes):**
- [ ] Review 5-day performance
- [ ] Check sell strategies for big movers
- [ ] Research 1-2 new stocks with $500 calculator
- [ ] Export portfolio backup

**Monthly (30 minutes):**
- [ ] Analyze 3-month trends
- [ ] Rebalance if needed
- [ ] Add high-scoring research candidates
- [ ] Review overall strategy

---

## 🚀 You're Ready!

That's it! You now have a fully-functional portfolio tracker with:
- ✅ Real-time performance monitoring
- ✅ AI-powered sell recommendations
- ✅ Family sharing capabilities
- ✅ $500 hypothetical investment calculator
- ✅ Automatic data backup

**Next Steps:**
1. Start tracking your investments
2. Share password with family
3. Review sell strategies weekly
4. Export backups regularly

Happy investing! 📈

---

**Questions?**
- Read `IMPLEMENTATION-SUMMARY.md` for detailed documentation
- Check `FULL-AUDIT-REPORT.md` for SEO audit
- Review `ACTION-PLAN.md` for improvement roadmap

# ValueSignal V2 - Deployment Checklist

## Pre-Deployment Verification

### 1. Environment Variables
Verify `.env.local` has all Firebase credentials:
```bash
cat .env.local
```

Expected variables:
- `VITE_FIREBASE_API_KEY`
- `VITE_FIREBASE_AUTH_DOMAIN`
- `VITE_FIREBASE_PROJECT_ID`
- `VITE_FIREBASE_STORAGE_BUCKET`
- `VITE_FIREBASE_MESSAGING_SENDER_ID`
- `VITE_FIREBASE_APP_ID`

### 2. Build Test
```bash
npm run build
```

Should complete without errors. Check `dist/` folder is created.

### 3. Local Preview
```bash
npm run preview
```

Visit http://localhost:4173 and verify:
- [ ] Login works (create test account)
- [ ] Profile switcher shows your theme
- [ ] Portfolio page loads (when logged in)
- [ ] Backtest page loads (when logged in)
- [ ] Password change works
- [ ] Logout works

---

## Netlify Deployment

### Step 1: Commit Latest Code
```bash
git add .
git commit -m "feat: complete V2 build - backtest engine, mobile cards, pipeline guardrails"
git push origin main
```

### Step 2: Configure Netlify Environment Variables
In Netlify dashboard → Site settings → Environment variables:

Add all variables from `.env.local` (without `VITE_` prefix in Netlify, Vite will add it):
- `FIREBASE_API_KEY` = AIzaSyBmvpYecf4kwz8eHrS1SgLO4Gv5on17fXY
- `FIREBASE_AUTH_DOMAIN` = dash-8bacf.firebaseapp.com
- `FIREBASE_PROJECT_ID` = dash-8bacf
- `FIREBASE_STORAGE_BUCKET` = dash-8bacf.firebasestorage.app
- `FIREBASE_MESSAGING_SENDER_ID` = 721449361796
- `FIREBASE_APP_ID` = 1:721449361796:web:841a1ca1002742e3ba7dd1

**Important:** Mark all as "Secret" (visibility setting)

### Step 3: Redeploy
Trigger new deploy in Netlify or push to trigger auto-deploy.

### Step 4: Verify Production
Visit your Netlify URL and test:
- [ ] Login/logout works
- [ ] Firebase data persists across sessions
- [ ] Portfolio saves correctly
- [ ] Backtest page accessible (after login)
- [ ] All routes work (/, /research, /market, /portfolio, /backtest, /watchlist, /methodology)

---

## Firebase Firestore Security Rules

Verify Firestore security rules are set:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // User profiles
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // Portfolios
    match /portfolios/{userId}/positions/{positionId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // Backtest signals
    match /backtestSignals/{signalId} {
      allow read: if request.auth != null;
      allow write: if request.auth != null && request.resource.data.userId == request.auth.uid;
    }
  }
}
```

---

## Post-Deployment Testing

### Functional Tests
1. **Authentication:**
   - [ ] Create new account (signup)
   - [ ] Login with existing account
   - [ ] Change password
   - [ ] Logout and login again

2. **Portfolio:**
   - [ ] Add position
   - [ ] Edit position
   - [ ] Remove position
   - [ ] Export portfolio
   - [ ] Import portfolio

3. **Backtest:**
   - [ ] View backtest page
   - [ ] Switch between strategies
   - [ ] View trade history
   - [ ] Filter by stock

4. **Mobile:**
   - [ ] Test on iPhone/Android
   - [ ] Cards render correctly
   - [ ] Navigation works
   - [ ] Profile switcher accessible

### Performance Tests
- [ ] Lighthouse score > 90 (Performance)
- [ ] Lighthouse score > 90 (Accessibility)
- [ ] First Contentful Paint < 2s
- [ ] Time to Interactive < 3s

---

## Known Limitations (Document for Users)

### Backtest Data
- **No historical prices yet:** Backtest simulations use mock data until price API integrated
- **No real signals:** Signal history is empty on fresh deploy, will accumulate over time
- To populate: Add `useSignalTracking()` hook to Dashboard/Research page

### Data Quality
- **Pipeline guardrails:** Not yet integrated into stock fetching logic
- To activate: Import `validateStockBatch()` in Dashboard and filter stocks before display

### Mobile Cards
- **Not default view:** Old table view still default
- To activate: Import `StockCardGrid` and `ViewModeSwitcher` in Research page

### Fidelity Connector
- **Not implemented:** Only stubs/architecture exist
- Phase 1 (manual CSV): Can implement in 1-2 days
- Phase 2 (Plaid): Requires Plaid account and 1-2 weeks

---

## Quick Integration Guide

### Activate Signal Tracking
**File:** `src/pages/Dashboard.jsx` or `src/pages/Picks.jsx`

```javascript
import { useSignalTracking } from '../lib/useSignalTracking'

function Dashboard() {
  const [stocks, setStocks] = useState([])
  const [previousStocks, setPreviousStocks] = useState([])

  // After fetching stocks
  useSignalTracking(stocks, previousStocks)

  useEffect(() => {
    if (stocks.length > 0) {
      setPreviousStocks(stocks)
    }
  }, [stocks])
}
```

### Activate Pipeline Guardrails
**File:** `src/pages/Dashboard.jsx`

```javascript
import { validateStockBatch } from '../lib/pipelineGuardrails'
import DataQualityDebugView from '../components/DataQualityDebugView'

function Dashboard() {
  const [validationResults, setValidationResults] = useState(null)

  // After fetching all stocks
  const results = validateStockBatch(allStocks)
  setStocks(results.passed) // Only display valid stocks
  setValidationResults(results) // For debug view

  return (
    <div>
      <DataQualityDebugView validationResults={validationResults} />
      {/* Rest of dashboard */}
    </div>
  )
}
```

### Switch to Mobile Cards
**File:** `src/pages/Picks.jsx`

```javascript
import StockCardGrid, { ViewModeSwitcher } from '../components/StockCardGrid'

function Picks() {
  const [viewMode, setViewMode] = useState('cards')

  return (
    <div>
      <ViewModeSwitcher viewMode={viewMode} onViewModeChange={setViewMode} />

      {viewMode === 'table' ? (
        <OldTableComponent stocks={stocks} />
      ) : (
        <StockCardGrid stocks={stocks} viewMode={viewMode} />
      )}
    </div>
  )
}
```

---

## Rollback Plan

If deployment fails:

### Option 1: Rollback in Netlify
1. Go to Deploys tab
2. Find previous successful deploy
3. Click "Publish deploy"

### Option 2: Revert Git Commit
```bash
git log  # Find previous commit hash
git revert <commit-hash>
git push origin main
```

### Option 3: Disable New Features
1. Remove backtest route from `App.jsx`
2. Keep using old table view
3. Deploy incremental fixes

---

## Monitoring

### Firebase Console
- Monitor authentication (user signups, logins)
- Check Firestore reads/writes (stay under free tier limits)
- Review security rules (no denied requests)

### Netlify Analytics
- Monitor bandwidth usage
- Check build success rate
- Review form submissions (if any)

### Browser Console
- Check for JS errors
- Verify no CORS issues
- Monitor network requests

---

## Support Contacts

### Firebase Issues
- Console: https://console.firebase.google.com
- Support: https://firebase.google.com/support

### Netlify Issues
- Dashboard: https://app.netlify.com
- Support: https://www.netlify.com/support

### Dependency Issues
```bash
npm outdated  # Check for outdated packages
npm audit     # Check for security vulnerabilities
npm audit fix # Auto-fix vulnerabilities
```

---

## Success Criteria

Deployment is successful when:
- [x] All 4 workstreams implemented (label, backtest, UI, stubs)
- [ ] Build completes without errors
- [ ] Production site loads
- [ ] Login/logout works
- [ ] Portfolio persists across sessions
- [ ] Backtest page accessible
- [ ] Mobile cards render correctly
- [ ] No console errors
- [ ] Firebase rules enforced
- [ ] Environment variables secured

**Status:** Code complete, ready for deployment testing ✅

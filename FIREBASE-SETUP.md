# Firebase Setup Guide

## Step 1: Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project" or "Create a project"
3. Name it "ValueSignal" (or your preferred name)
4. Disable Google Analytics (optional, not needed for this app)
5. Click "Create project"

---

## Step 2: Enable Authentication

1. In Firebase Console, click "Authentication" in the left sidebar
2. Click "Get started"
3. Go to "Sign-in method" tab
4. Enable "Email/Password"
5. Click "Save"

---

## Step 3: Create Firestore Database

1. Click "Firestore Database" in the left sidebar
2. Click "Create database"
3. Choose "Start in **production mode**"
4. Select a Cloud Firestore location (choose closest to your users)
5. Click "Enable"

---

## Step 4: Set Firestore Security Rules

1. In Firestore Database, go to "Rules" tab
2. Replace the rules with:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Users can only read/write their own data
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // User profiles are readable by anyone, writable by owner
    match /profiles/{userId} {
      allow read: if request.auth != null;
      allow write: if request.auth != null && request.auth.uid == userId;
    }

    // Portfolio data is private to each user
    match /portfolios/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }

    // Backtest signals are readable by all authenticated users
    match /backtestSignals/{signalId} {
      allow read: if request.auth != null;
      allow write: if false; // Only server/pipeline can write
    }
  }
}
```

3. Click "Publish"

---

## Step 5: Get Firebase Configuration

1. In Firebase Console, click the gear icon (⚙️) > "Project settings"
2. Scroll down to "Your apps"
3. Click the web icon (`</>`) to add a web app
4. Register app name: "ValueSignal Web"
5. Don't enable Firebase Hosting (we're using Netlify)
6. Click "Register app"
7. Copy the `firebaseConfig` object

---

## Step 6: Configure Environment Variables

1. Open your project's `.env.local` file (create if it doesn't exist)
2. Add your Firebase credentials:

```env
# Firebase Configuration
VITE_FIREBASE_API_KEY=AIza...your_api_key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=123456789012
VITE_FIREBASE_APP_ID=1:123456789012:web:abc123def456
```

3. Save the file
4. **Never commit `.env.local` to Git** (it's already in `.gitignore`)

---

## Step 7: Create Family Profiles (One-time Setup)

After deploying with Firebase enabled, you'll need to create the 4 family accounts:

### Option A: Manual Creation (Recommended for security)

1. Open the app
2. Click "Create New Profile"
3. Fill in:
   - **Dad's Profile:**
     - Email: dad@family.local (or real email)
     - Password: (choose strong password)
     - Display Name: Dad
     - Color Theme: Black & Gold (auto-selected)

   - **Mom's Profile:**
     - Email: mom@family.local
     - Password: (choose strong password)
     - Display Name: Mom
     - Color Theme: Crimson Red & Cream (auto-selected)

   - **Jay's Profile:**
     - Email: jay@family.local
     - Password: (choose strong password)
     - Display Name: Jay
     - Color Theme: Black & Red (auto-selected)

   - **Your Profile:**
     - Email: your@family.local
     - Password: (choose strong password)
     - Display Name: (Your name)
     - Color Theme: Forest Green & Cream (auto-selected)

### Option B: Pre-seed via Firebase Console

1. Go to Firebase Console > Authentication > Users
2. Click "Add user"
3. Enter email and password for each family member
4. The app will detect the email and auto-assign color themes

---

## Step 8: Deploy to Netlify

1. Add environment variables to Netlify:
   - Go to Netlify dashboard > Site settings > Environment variables
   - Add all `VITE_FIREBASE_*` variables
   - Values should match your `.env.local`

2. Redeploy:
```bash
npm run build
# Netlify will auto-deploy if connected to Git
```

---

## Security Best Practices

1. **Enable App Check** (optional but recommended):
   - In Firebase Console > App Check
   - Helps prevent abuse of your Firebase resources

2. **Monitor Usage**:
   - Check Firebase Console > Usage and billing
   - Free Spark plan limits:
     - 50K reads/day (Firestore)
     - 20K writes/day (Firestore)
     - More than enough for family use

3. **Backup Data**:
   - Firestore doesn't auto-backup on free plan
   - Use the export feature in Portfolio page
   - Consider scheduled Cloud Functions for backups (requires Blaze plan)

---

## Troubleshooting

### "Firebase: Error (auth/configuration-not-found)"
- Check that all `VITE_FIREBASE_*` variables are set in `.env.local`
- Restart dev server: `npm run dev`

### "Missing or insufficient permissions"
- Verify Firestore security rules are published
- Check that user is authenticated

### "Quota exceeded"
- Check Firebase Console > Usage
- Free plan limits are generous for small family use
- Consider upgrading to Blaze (pay-as-you-go) if needed

---

## Migration from LocalStorage

The app will automatically migrate existing portfolio data from localStorage to Firebase on first login. The process:

1. User logs in for the first time
2. App checks for existing `valuesignal.portfolio.*` data in localStorage
3. If found, prompts: "Migrate existing portfolio to cloud?"
4. If yes, uploads to Firestore and marks as migrated
5. Future logins pull from Firestore instead

---

## What's Stored in Firebase

### `/users/{userId}`
```json
{
  "email": "dad@family.local",
  "displayName": "Dad",
  "colorTheme": {
    "primary": "#000000",
    "accent": "#FFD700",
    "name": "Black & Gold"
  },
  "darkMode": true,
  "createdAt": "2026-07-30T12:00:00Z",
  "lastLogin": "2026-07-30T14:30:00Z"
}
```

### `/portfolios/{userId}/positions/{positionId}`
```json
{
  "ticker": "AAPL",
  "shares": 10,
  "costBasis": 150.25,
  "purchaseDate": "2026-06-15",
  "addedAt": "2026-07-30T12:00:00Z"
}
```

### `/backtestSignals/{signalId}`
```json
{
  "ticker": "MSFT",
  "type": "entry",
  "timestamp": "2026-07-15T09:30:00Z",
  "rank": 3,
  "score": 87,
  "stance": "Attractive",
  "price": 420.30
}
```

---

## Cost Estimate

**Spark Plan (Free):**
- ✅ Up to 50K document reads/day
- ✅ Up to 20K document writes/day
- ✅ 1 GB storage
- ✅ 10 GB/month transfer
- **Estimated family usage:** <1% of limits

**If you need more** (unlikely for family use):
- Blaze Plan: Pay only for what you use
- ~$0.06 per 100K reads
- ~$0.18 per 100K writes
- Estimated cost for family: **$0-1/month**

---

You're now ready to use Firebase-powered profiles with cloud sync! 🚀

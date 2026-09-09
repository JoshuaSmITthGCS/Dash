// Shared Firestore connection/credential logic for every portfolio CLI script
// (sync-portfolio-firebase.mjs, reconcile-portfolio-activity.mjs, audit-portfolio-ledger.mjs,
// rebuild-trade-ledger.mjs). Extracted so all four scripts read and write through one
// definition of "how to reach this account's data" and cannot drift from each other.
//
// Two ways to authenticate, picked automatically:
//
//   - SIGN-IN (default when no service account is configured). Signs in as the account with
//     its own app password, using the VITE_FIREBASE_* client config already in .env.local for
//     `npm run dev`. Nothing new to configure, and writes go through firestore.rules exactly
//     as the browser's would -- the rules grant a signed-in user their own portfolios/{uid}.
//     The password is prompted for, or read from PORTFOLIO_SYNC_PASSWORD; it is never taken
//     as a flag, which would leave it in shell history.
//   - ADMIN, when FIREBASE_SERVICE_ACCOUNT_JSON is set. Needs no password and can sync any
//     account by uid, but bypasses firestore.rules by design -- a server-side secret.

import { createInterface } from 'node:readline'
import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'
import { getFirestore } from 'firebase-admin/firestore'
import { initializeApp as initializeClientApp } from 'firebase/app'
import { getAuth as getClientAuth, signInWithEmailAndPassword, signOut } from 'firebase/auth'
import {
  collection as clientCollection,
  doc as clientDoc,
  getDoc as clientGetDoc,
  getDocs as clientGetDocs,
  getFirestore as getClientFirestore,
  terminate as terminateClient,
  writeBatch as clientWriteBatch,
} from 'firebase/firestore'

// Firestore caps a batch at 500 writes.
export const BATCH_LIMIT = 500

// Every network call is bounded and announced before it starts. firebase-admin retries a
// blocked connection with long backoff and prints nothing while it does, so an unreachable
// Google endpoint -- a proxy, a VPN, an offline machine -- otherwise looks like the script
// silently froze, with no way to tell which step it froze on.
export const NETWORK_TIMEOUT_MS = 30_000

export const step = (message) => process.stdout.write(`${message}\n`)

export function withTimeout(promise, what, ms = NETWORK_TIMEOUT_MS) {
  let timer
  const limit = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(
        `${what} did not respond within ${ms / 1000}s.\n`
        + '  This step talks to Google. A proxy, VPN, or offline machine blocks it silently.\n'
        + '  Check connectivity, then re-run — nothing has been written.',
      )),
      ms,
    )
    timer.unref?.()
  })
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer))
}

function adminCredential() {
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON
  if (!raw) return null
  let credential
  try { credential = JSON.parse(raw) } catch { throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON.') }
  const missing = ['project_id', 'client_email', 'private_key'].filter((field) => !credential[field])
  if (missing.length) {
    throw new Error(`FIREBASE_SERVICE_ACCOUNT_JSON is missing ${missing.join(', ')}. `
      + 'Use the whole downloaded service-account key file, not a fragment of it.')
  }
  return credential
}

function clientConfig() {
  const config = {
    apiKey: process.env.VITE_FIREBASE_API_KEY,
    authDomain: process.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: process.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.VITE_FIREBASE_APP_ID,
  }
  return config.apiKey && config.projectId ? config : null
}

/** Reads a secret without echoing it, so it never lands in a terminal scrollback. */
function promptPassword(question) {
  if (!process.stdin.isTTY) {
    return Promise.reject(new Error(
      'No terminal to prompt for a password on. Set PORTFOLIO_SYNC_PASSWORD instead, '
      + 'or configure FIREBASE_SERVICE_ACCOUNT_JSON to use admin credentials.',
    ))
  }
  return new Promise((resolve) => {
    const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true })
    rl._writeToOutput = (chunk) => { if (chunk.includes(question)) rl.output.write(question) }
    rl.question(question, (answer) => {
      rl.close()
      process.stdout.write('\n')
      resolve(answer)
    })
  })
}

/**
 * One interface over the two credential paths, so plan/report/commit logic in every caller
 * never branches on which is in use and behaves identically either way.
 *
 * The returned backend's `commit(apply)` batches writes across five sub-collections:
 * positions, intradaySnapshots, tracking/state, activity, and closedPositions -- the same five
 * the app itself writes through useFirebasePortfolio.js and usePortfolioTracking.js. A script
 * that needs a doc ref not listed here should add it to both branches below, never construct
 * a raw path inline, so admin and sign-in mode cannot drift from each other.
 */
export async function connectPortfolioBackend(options) {
  const credential = adminCredential()
  if (credential) {
    step(`Admin credentials loaded for project ${credential.project_id}.`)
    const app = getApps().length ? getApps()[0] : initializeApp({ credential: cert(credential) })
    const db = getFirestore(app)
    let uid = options.uid
    if (!uid) {
      step(`Resolving ${options.email} via Firebase Auth…`)
      try {
        uid = (await withTimeout(getAuth(app).getUserByEmail(options.email), 'Firebase Auth')).uid
      } catch (error) {
        if (error.code === 'auth/user-not-found') {
          throw new Error(`No Firebase user has the email ${options.email}. `
            + 'Sign in to the app once with it, or pass --uid instead.')
        }
        throw error
      }
    }
    const col = (name) => db.collection('portfolios').doc(uid).collection(name)
    return {
      mode: 'admin',
      uid,
      readPositions: () => withTimeout(col('positions').get(), 'Firestore read')
        .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
      readClosedTickers: () => withTimeout(col('closedPositions').get(), 'Firestore read')
        .then((snapshot) => snapshot.docs.map((item) => item.data()?.ticker || item.id)),
      readClosedPositions: () => withTimeout(col('closedPositions').get(), 'Firestore read')
        .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
      readTrackingState: () => withTimeout(col('tracking').doc('state').get(), 'Firestore read')
        .then((snapshot) => (snapshot.exists ? snapshot.data() : null)),
      readActivity: () => withTimeout(col('activity').get(), 'Firestore read')
        .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
      readSnapshots: () => withTimeout(col('intradaySnapshots').get(), 'Firestore read')
        .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
      commit: (apply) => {
        const batch = db.batch()
        apply({
          positionDoc: (id) => col('positions').doc(id),
          snapshotDoc: (id) => col('intradaySnapshots').doc(id),
          trackingDoc: () => col('tracking').doc('state'),
          activityDoc: (id) => col('activity').doc(id),
          closedPositionDoc: (ticker) => col('closedPositions').doc(ticker),
          set: (ref, data, merge) => batch.set(ref, data, merge ? { merge: true } : {}),
          delete: (ref) => batch.delete(ref),
        })
        return withTimeout(batch.commit(), 'Firestore write')
      },
      close: async () => {
        try { await db.terminate?.() } catch { /* best effort */ }
      },
    }
  }

  const config = clientConfig()
  if (!config) {
    throw new Error(
      'No Firebase credentials found.\n'
      + '  Sign-in mode needs VITE_FIREBASE_API_KEY and VITE_FIREBASE_PROJECT_ID in .env.local\n'
      + '  (the same values `npm run dev` uses). Admin mode needs FIREBASE_SERVICE_ACCOUNT_JSON.',
    )
  }
  if (options.uid) {
    throw new Error('--uid needs admin credentials. Sign-in mode can only reach the account it '
      + 'signs in as, so pass --email instead.')
  }

  const password = process.env.PORTFOLIO_SYNC_PASSWORD
    || await promptPassword(`Password for ${options.email}: `)
  if (!password) throw new Error('No password given, so there is nothing to sign in with.')

  step(`Signing in as ${options.email} on project ${config.projectId}…`)
  const app = initializeClientApp(config, 'portfolio-cli')
  const auth = getClientAuth(app)
  let user
  try {
    user = (await withTimeout(signInWithEmailAndPassword(auth, options.email, password), 'Firebase sign-in')).user
  } catch (error) {
    const friendly = {
      'auth/invalid-credential': 'Email or password not accepted.',
      'auth/wrong-password': 'Wrong password.',
      'auth/user-not-found': `No account for ${options.email}.`,
      'auth/too-many-requests': 'Too many attempts; Firebase has throttled this account briefly.',
      'auth/network-request-failed': 'Could not reach Firebase. Check connectivity, proxy, or VPN.',
      'auth/invalid-email': `${options.email} is not a valid email address.`,
      'auth/api-key-not-valid.-please-pass-a-valid-api-key.':
        'VITE_FIREBASE_API_KEY in .env.local is not a valid key for this project.',
    }[error.code]
    throw new Error(friendly || error.message)
  }
  const db = getClientFirestore(app)
  const uid = user.uid
  const col = (name) => clientCollection(db, 'portfolios', uid, name)
  const docIn = (name, id) => clientDoc(db, 'portfolios', uid, name, id)
  return {
    mode: 'sign-in',
    uid,
    readPositions: () => withTimeout(clientGetDocs(col('positions')), 'Firestore read')
      .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
    readClosedTickers: () => withTimeout(clientGetDocs(col('closedPositions')), 'Firestore read')
      .then((snapshot) => snapshot.docs.map((item) => item.data()?.ticker || item.id)),
    readClosedPositions: () => withTimeout(clientGetDocs(col('closedPositions')), 'Firestore read')
      .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
    readTrackingState: () => withTimeout(clientGetDoc(docIn('tracking', 'state')), 'Firestore read')
      .then((snapshot) => (snapshot.exists() ? snapshot.data() : null)),
    readActivity: () => withTimeout(clientGetDocs(col('activity')), 'Firestore read')
      .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
    readSnapshots: () => withTimeout(clientGetDocs(col('intradaySnapshots')), 'Firestore read')
      .then((snapshot) => snapshot.docs.map((item) => ({ id: item.id, ...item.data() }))),
    commit: (apply) => {
      const batch = clientWriteBatch(db)
      apply({
        positionDoc: (id) => docIn('positions', id),
        snapshotDoc: (id) => docIn('intradaySnapshots', id),
        trackingDoc: () => docIn('tracking', 'state'),
        activityDoc: (id) => docIn('activity', id),
        closedPositionDoc: (ticker) => docIn('closedPositions', ticker),
        set: (ref, data, merge) => batch.set(ref, data, merge ? { merge: true } : {}),
        delete: (ref) => batch.delete(ref),
      })
      return withTimeout(batch.commit(), 'Firestore write')
    },
    close: async () => {
      try { await signOut(auth) } catch { /* best effort */ }
      try { await terminateClient(db) } catch { /* best effort */ }
    },
  }
}

/** Shared account-selection argument parsing: --email or --uid, never both. */
export function parseAccountArguments(argv, index, options) {
  const argument = argv[index]
  if (argument === '--email') { options.email = argv[index + 1]; return 2 }
  if (argument === '--uid') { options.uid = argv[index + 1]; return 2 }
  return 0
}

export function requireAccountSelection(options) {
  if (!options.help && !options.email && !options.uid) {
    throw new Error('Pass --email <address> or --uid <id> to name the account.')
  }
  if (options.email && options.uid) {
    throw new Error('Pass either --email or --uid, not both.')
  }
}

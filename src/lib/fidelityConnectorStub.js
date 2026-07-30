/**
 * Fidelity Brokerage Connector Stub
 *
 * Design for Fidelity integration (read-only portfolio sync).
 * NOT IMPLEMENTED - architecture and API design only.
 *
 * Goals:
 * 1. Read-only access to Fidelity accounts
 * 2. Automatic portfolio sync (holdings, transactions, performance)
 * 3. OAuth-based authentication (never store credentials)
 * 4. Real-time or scheduled updates
 * 5. Multi-account support (multiple Fidelity accounts per user)
 */

/**
 * Fidelity API Integration Options
 */
export const FIDELITY_INTEGRATION_OPTIONS = {
  official: {
    name: 'Fidelity Wealth Management API',
    status: 'Not publicly available',
    description: 'Fidelity does not offer a public API for retail accounts',
    pros: [],
    cons: [
      'No public API access',
      'Enterprise/institutional only',
      'Not available for retail users'
    ],
    recommendation: 'Not viable for consumer app'
  },

  plaid: {
    name: 'Plaid Investments API',
    status: 'Available',
    description: 'Third-party aggregator supporting Fidelity connections',
    pros: [
      'Supports Fidelity and 12,000+ institutions',
      'OAuth-based, no credential storage',
      'Real-time balance and holdings updates',
      'Standardized API across brokerages',
      'SOC 2 Type II certified',
      'Free tier available for development'
    ],
    cons: [
      'Cost: $0.20-$1.00 per user/month (volume pricing)',
      'Requires Plaid account verification',
      'Some features require paid tier',
      'Potential sync delays (depends on institution)'
    ],
    recommendation: 'RECOMMENDED - industry standard for brokerage connections',
    documentation: 'https://plaid.com/docs/investments/'
  },

  yodlee: {
    name: 'Yodlee APIs',
    status: 'Available',
    description: 'Alternative aggregator supporting Fidelity',
    pros: [
      'Supports Fidelity and major brokerages',
      'Read-only access',
      'Established provider (owned by Envestnet)'
    ],
    cons: [
      'More expensive than Plaid',
      'Complex onboarding',
      'Enterprise-focused pricing'
    ],
    recommendation: 'Alternative to Plaid, but higher barrier to entry'
  },

  manual: {
    name: 'Manual CSV Import',
    status: 'Available (implement immediately)',
    description: 'Users export portfolio from Fidelity and upload CSV',
    pros: [
      'No API costs',
      'No OAuth complexity',
      'Full user control',
      'Works for ANY brokerage',
      'Can implement quickly'
    ],
    cons: [
      'Manual update process',
      'User friction',
      'No real-time sync',
      'Requires user to export data'
    ],
    recommendation: 'START HERE - implement as V2 feature, add Plaid later'
  }
}

/**
 * Recommended Architecture: Plaid Integration
 */
export const PLAID_INTEGRATION_DESIGN = {
  flow: [
    '1. User clicks "Connect Fidelity" in Portfolio page',
    '2. Open Plaid Link modal (Plaid SDK)',
    '3. User logs into Fidelity via Plaid (OAuth-like flow)',
    '4. Plaid returns access_token and item_id',
    '5. Store encrypted tokens in Firestore (user-specific)',
    '6. Fetch holdings via Plaid Investments API',
    '7. Sync to user portfolio in Firestore',
    '8. Schedule daily/weekly automatic syncs'
  ],

  components: {
    frontend: [
      'PlaidLink component (React SDK)',
      'ConnectBrokerageButton',
      'SyncStatusIndicator',
      'LastSyncTimestamp',
      'ManualRefreshButton',
      'DisconnectBrokerageButton'
    ],
    backend: [
      'plaidService.js - Plaid API wrapper',
      'syncScheduler.js - Cron job for automatic syncs',
      'tokenEncryption.js - Encrypt/decrypt Plaid tokens',
      'holdingsMapper.js - Map Plaid format to app format',
      'syncHistory.js - Track sync events and errors'
    ],
    database: {
      collection: 'brokerageConnections',
      schema: {
        userId: 'string',
        provider: 'plaid',
        institution: 'fidelity',
        itemId: 'string (encrypted)',
        accessToken: 'string (encrypted)',
        accountIds: 'string[]',
        lastSync: 'timestamp',
        syncStatus: 'connected|syncing|error|disconnected',
        errorMessage: 'string?',
        createdAt: 'timestamp'
      }
    }
  },

  plaidEndpoints: {
    '/link/token/create': 'Create Link token for Plaid UI',
    '/item/public_token/exchange': 'Exchange public token for access token',
    '/investments/holdings/get': 'Fetch holdings and balances',
    '/investments/transactions/get': 'Fetch investment transactions',
    '/accounts/balance/get': 'Fetch account balances',
    '/item/remove': 'Disconnect account'
  },

  security: [
    'Store Plaid tokens encrypted at rest (AES-256)',
    'Use environment variables for Plaid client_id and secret',
    'Validate webhook signatures from Plaid',
    'Implement token rotation',
    'Rate limit API calls per Plaid TOS',
    'Log all sync events for audit trail',
    'Alert user on sync errors'
  ]
}

/**
 * Manual CSV Import Design (V2 Implementation)
 */
export const MANUAL_IMPORT_DESIGN = {
  userFlow: [
    '1. User goes to Fidelity.com → Accounts → Positions',
    '2. Click "Download" → Select CSV format',
    '3. Return to ValueSignal → Portfolio → "Import from CSV"',
    '4. Upload Fidelity CSV file',
    '5. App parses CSV and maps columns',
    '6. Preview import (show matched tickers, warnings)',
    '7. User confirms → positions added to portfolio',
    '8. Show last import timestamp'
  ],

  csvFormat: {
    expectedColumns: [
      'Symbol',
      'Description',
      'Quantity',
      'Last Price',
      'Current Value',
      'Cost Basis',
      'Gain/Loss',
      'Gain/Loss %',
      'Account Name'
    ],
    parsing: {
      ticker: 'Symbol column',
      shares: 'Quantity column (parse as float)',
      costBasis: 'Cost Basis column (parse currency)',
      currentValue: 'Current Value column (parse currency)',
      account: 'Account Name column (for multi-account users)'
    },
    validation: [
      'Check for valid ticker symbols',
      'Verify numeric fields parse correctly',
      'Warn on missing cost basis',
      'Alert if duplicate tickers (sum quantities)'
    ]
  },

  components: {
    CSVUploader: 'File upload with drag-and-drop',
    CSVParser: 'Parse and validate CSV format',
    ImportPreview: 'Show matched positions before import',
    ImportSummary: 'Show import results (success/warnings/errors)',
    LastImportIndicator: 'Display when portfolio was last imported'
  }
}

/**
 * Comparison: Manual vs API Sync
 */
export const SYNC_COMPARISON = {
  manual: {
    implementation: 'Easy (1-2 days)',
    cost: '$0',
    updateFrequency: 'User-driven (weekly/monthly)',
    userEffort: 'High (manual export/import)',
    accuracy: 'High (direct from brokerage)',
    brokerageSupport: 'All brokerages (universal CSV)',
    security: 'No API tokens to manage',
    maintenance: 'Low'
  },
  plaid: {
    implementation: 'Medium (1-2 weeks)',
    cost: '$0.20-$1/user/month',
    updateFrequency: 'Automatic (daily/real-time)',
    userEffort: 'Low (one-time OAuth)',
    accuracy: 'High (real-time from brokerage)',
    brokerageSupport: '12,000+ institutions',
    security: 'OAuth tokens, encryption required',
    maintenance: 'Medium (webhook handling, error recovery)'
  }
}

/**
 * Implementation Phases
 */
export const IMPLEMENTATION_PHASES = {
  phase1_v2: {
    name: 'Manual CSV Import',
    timeline: '1-2 days',
    features: [
      'CSV file upload UI',
      'Fidelity CSV parser',
      'Import preview and validation',
      'Add positions to portfolio',
      'Last import timestamp'
    ],
    blockers: 'None - can implement immediately'
  },

  phase2_v3: {
    name: 'Plaid Integration (Read-Only)',
    timeline: '1-2 weeks',
    features: [
      'Plaid account setup and API keys',
      'PlaidLink component integration',
      'Token encryption and storage',
      'Initial holdings sync',
      'Manual refresh button',
      'Disconnect brokerage option'
    ],
    blockers: [
      'Need Plaid developer account',
      'Implement backend token encryption',
      'Set up Firestore schema for connections'
    ]
  },

  phase3_future: {
    name: 'Automatic Sync & Multi-Brokerage',
    timeline: '2-4 weeks',
    features: [
      'Scheduled automatic syncs (daily)',
      'Webhook handlers for real-time updates',
      'Support multiple brokerages (Schwab, Vanguard, etc)',
      'Sync history and error recovery',
      'Performance attribution across accounts',
      'Tax lot tracking'
    ],
    blockers: [
      'Need backend infrastructure for cron jobs',
      'Webhook endpoint setup',
      'Advanced error handling'
    ]
  }
}

/**
 * Cost Estimate (Plaid Integration)
 */
export function estimatePlaidCost(numUsers) {
  const pricePerUser = 0.50 // Average Plaid pricing (volume discount)
  const monthlyCost = numUsers * pricePerUser
  const annualCost = monthlyCost * 12

  return {
    numUsers,
    pricePerUser,
    monthlyCost,
    annualCost,
    breakEvenUsers: 0, // Always costs money, no break-even
    recommendation: numUsers < 10 ? 'Start with manual CSV import' :
                    numUsers < 100 ? 'Consider Plaid if user demand is high' :
                    'Plaid recommended for scale and user experience'
  }
}

/**
 * Stub functions for future implementation
 */

// Phase 1 (V2): Manual Import
export async function importFidelityCSV(csvFile, userId) {
  // TODO: Implement CSV parsing and validation
  throw new Error('Not implemented - stub only')
}

// Phase 2 (V3): Plaid Integration
export async function connectPlaidAccount(userId, publicToken) {
  // TODO: Exchange public token for access token, store encrypted
  throw new Error('Not implemented - stub only')
}

export async function syncPlaidHoldings(userId, connectionId) {
  // TODO: Fetch holdings from Plaid, update portfolio
  throw new Error('Not implemented - stub only')
}

export async function disconnectPlaidAccount(userId, connectionId) {
  // TODO: Remove Plaid item, delete tokens
  throw new Error('Not implemented - stub only')
}

// Phase 3 (Future): Scheduled Sync
export async function scheduleAutomaticSync(userId, connectionId, frequency = 'daily') {
  // TODO: Set up cron job for automatic portfolio sync
  throw new Error('Not implemented - stub only')
}

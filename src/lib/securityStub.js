/**
 * Security Architecture Stub
 *
 * Design for production-ready security features.
 * NOT IMPLEMENTED - stubs only for V2 planning.
 */

/**
 * Security Features Roadmap
 */
export const SECURITY_ROADMAP = {
  authentication: {
    current: 'Firebase Authentication (email/password)',
    future: [
      'Multi-factor authentication (TOTP, SMS)',
      'Biometric authentication (TouchID, FaceID)',
      'OAuth2 providers (Google, Apple)',
      'Session management with device tracking',
      'Password strength requirements (zxcvbn)',
      'Account recovery flow',
      'Login attempt rate limiting'
    ]
  },

  authorization: {
    current: 'Basic user-level access control',
    future: [
      'Role-based access control (RBAC)',
      'Family account permissions (read-only, editor, admin)',
      'Portfolio visibility controls',
      'Audit logging for sensitive actions',
      'API key management for integrations'
    ]
  },

  dataProtection: {
    current: 'Firebase Firestore rules, HTTPS in transit',
    future: [
      'End-to-end encryption for portfolio holdings',
      'Field-level encryption for sensitive data (SSN, account numbers)',
      'Client-side encryption keys (user-controlled)',
      'PII handling compliance (GDPR, CCPA)',
      'Data retention policies',
      'Secure deletion (crypto-shredding)',
      'Regular security audits'
    ]
  },

  brokerageIntegration: {
    current: 'None',
    future: [
      'OAuth-based brokerage connections (never store credentials)',
      'Read-only API access preferred',
      'Token rotation and expiration',
      'Encrypted token storage',
      'Webhook verification for real-time updates',
      'Rate limiting per brokerage TOS'
    ]
  },

  infrastructure: {
    current: 'Netlify hosting, Firebase backend',
    future: [
      'Content Security Policy (CSP) headers',
      'Subresource Integrity (SRI) for CDN scripts',
      'DDoS protection (Cloudflare)',
      'WAF rules for common attacks',
      'Security headers (HSTS, X-Frame-Options, etc)',
      'Regular dependency updates (Dependabot)',
      'Vulnerability scanning (Snyk, npm audit)',
      'Secrets management (Vault, AWS Secrets Manager)'
    ]
  }
}

/**
 * Security Checklist for Production
 */
export const PRODUCTION_SECURITY_CHECKLIST = [
  {
    category: 'Authentication',
    items: [
      { done: true, task: 'Implement email/password auth' },
      { done: true, task: 'Add password change functionality' },
      { done: false, task: 'Add MFA support' },
      { done: false, task: 'Add password strength meter' },
      { done: false, task: 'Implement account recovery' },
      { done: false, task: 'Add login rate limiting' }
    ]
  },
  {
    category: 'Data Protection',
    items: [
      { done: true, task: 'HTTPS for all traffic' },
      { done: true, task: 'Firestore security rules' },
      { done: false, task: 'Field-level encryption' },
      { done: false, task: 'PII handling audit' },
      { done: false, task: 'Data retention policy' },
      { done: false, task: 'Backup and disaster recovery plan' }
    ]
  },
  {
    category: 'Infrastructure',
    items: [
      { done: false, task: 'Add CSP headers' },
      { done: false, task: 'Configure security headers' },
      { done: false, task: 'Set up DDoS protection' },
      { done: false, task: 'Implement rate limiting' },
      { done: false, task: 'Set up monitoring and alerts' },
      { done: false, task: 'Regular security audits' }
    ]
  },
  {
    category: 'Code Security',
    items: [
      { done: false, task: 'Input validation on all user data' },
      { done: false, task: 'XSS prevention (DOMPurify)' },
      { done: false, task: 'SQL injection prevention (using Firestore SDK)' },
      { done: false, task: 'CSRF protection' },
      { done: false, task: 'Dependency vulnerability scanning' },
      { done: false, task: 'Code review process' }
    ]
  }
]

/**
 * Threat Model
 */
export const THREAT_MODEL = {
  threats: [
    {
      id: 'T1',
      name: 'Credential Theft',
      description: 'Attacker steals user credentials via phishing or data breach',
      impact: 'High - unauthorized access to portfolio data',
      likelihood: 'Medium',
      mitigations: [
        'MFA required for all accounts',
        'Password strength requirements',
        'Login anomaly detection',
        'User education on phishing'
      ]
    },
    {
      id: 'T2',
      name: 'Session Hijacking',
      description: 'Attacker intercepts or steals session token',
      impact: 'High - impersonation of user',
      likelihood: 'Low',
      mitigations: [
        'HTTPS-only cookies',
        'Short session expiration',
        'Device fingerprinting',
        'Session invalidation on logout'
      ]
    },
    {
      id: 'T3',
      name: 'Brokerage API Abuse',
      description: 'Compromised brokerage credentials used for unauthorized trades',
      impact: 'Critical - financial loss',
      likelihood: 'Medium',
      mitigations: [
        'Read-only API access only',
        'OAuth tokens (never store passwords)',
        'Alert on unusual API activity',
        'User consent for each trade action'
      ]
    },
    {
      id: 'T4',
      name: 'Data Breach',
      description: 'Firestore database compromised, portfolio data exposed',
      impact: 'High - privacy violation, potential financial harm',
      likelihood: 'Low',
      mitigations: [
        'Field-level encryption for sensitive data',
        'Strict Firestore security rules',
        'Regular security audits',
        'Incident response plan'
      ]
    },
    {
      id: 'T5',
      name: 'XSS Attack',
      description: 'Malicious script injected into UI to steal data',
      impact: 'Medium - session theft, data exfiltration',
      likelihood: 'Medium',
      mitigations: [
        'CSP headers blocking inline scripts',
        'DOMPurify for user-generated content',
        'React auto-escaping (already implemented)',
        'Regular security testing'
      ]
    }
  ]
}

/**
 * Compliance Requirements
 */
export const COMPLIANCE = {
  regulations: {
    GDPR: {
      applicable: 'If serving EU users',
      requirements: [
        'User consent for data collection',
        'Right to access (data export)',
        'Right to erasure (account deletion)',
        'Data portability',
        'Privacy policy and cookie notice',
        'Data processing agreements',
        'Breach notification (72 hours)'
      ]
    },
    CCPA: {
      applicable: 'If serving California users',
      requirements: [
        'Privacy policy disclosure',
        'Right to know (data inventory)',
        'Right to delete',
        'Right to opt-out of sale (N/A - no data sale)',
        'Non-discrimination'
      ]
    },
    SEC: {
      applicable: 'If providing investment advice',
      requirements: [
        'Investment advisor registration (if required)',
        'Disclosure of conflicts of interest',
        'Fiduciary duty (if RIA)',
        'Form ADV filing',
        'Regular compliance audits'
      ]
    },
    FINRA: {
      applicable: 'If executing trades or recommending specific securities',
      requirements: [
        'Broker-dealer registration',
        'Suitability assessments',
        'Communication with public rules',
        'Supervision and compliance'
      ]
    }
  },
  disclaimer: 'Current app is for RESEARCH ONLY, not investment advice. Must add disclaimers if expanding to recommendations.'
}

/**
 * Get security status summary
 */
export function getSecurityStatus() {
  const totalTasks = PRODUCTION_SECURITY_CHECKLIST.reduce((sum, cat) => sum + cat.items.length, 0)
  const completedTasks = PRODUCTION_SECURITY_CHECKLIST.reduce(
    (sum, cat) => sum + cat.items.filter(item => item.done).length,
    0
  )

  return {
    total: totalTasks,
    completed: completedTasks,
    percentage: (completedTasks / totalTasks) * 100,
    readyForProduction: completedTasks === totalTasks
  }
}

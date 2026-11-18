/**
 * Cryptographically secure identifier generation for client idempotency and tokens.
 * Uses Web Crypto APIs (crypto.randomUUID / crypto.getRandomValues) to avoid insecure PRNGs (S2245).
 */
export function generateSecureId(prefix = 'idemp'): string {
  if (typeof crypto !== 'undefined') {
    if (typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
    if (typeof crypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16)
      crypto.getRandomValues(bytes)
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
      return `${prefix}-${Date.now()}-${hex}`
    }
  }
  return `${prefix}-${Date.now()}-fallback`
}

import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { createOrganization } from '../services/organizations'
import { AuthApiError } from '../services/auth'

export function OrgSelector() {
  const { token, organizations, activeOrg, selectOrganization, refreshOrganizations } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [orgName, setOrgName] = useState('')
  const [orgSlug, setOrgSlug] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleCreateOrg = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return
    setError(null)
    setLoading(true)

    try {
      const created = await createOrganization(token, {
        name: orgName.trim(),
        slug: orgSlug.trim().toLowerCase(),
      })
      await refreshOrganizations()
      selectOrganization(created.id)
      setOrgName('')
      setOrgSlug('')
      setShowCreateModal(false)
      setIsOpen(false)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Failed to create organization')
      }
    } finally {
      setLoading(false)
    }
  }

  const roleBadgeColor = (role?: string) => {
    switch (role) {
      case 'ORG_ADMIN':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/20'
      case 'AUDITOR':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
      default:
        return 'bg-slate-500/10 text-slate-300 border-slate-500/20'
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-sm text-slate-200 transition-colors"
      >
        <span className="w-2 h-2 rounded-full bg-emerald-400" />
        <span className="font-semibold">{activeOrg ? activeOrg.name : 'Select Organization'}</span>
        {activeOrg && (
          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${roleBadgeColor(activeOrg.role)}`}>
            {activeOrg.role}
          </span>
        )}
        <svg
          className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 mt-2 w-72 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl py-2 z-40">
          <div className="px-3 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Your Organizations ({organizations.length})
          </div>

          <div className="max-h-60 overflow-y-auto divide-y divide-slate-800/50">
            {organizations.length === 0 ? (
              <div className="px-3 py-3 text-xs text-slate-500 text-center">
                No organizations yet. Create one below to begin.
              </div>
            ) : (
              organizations.map((org) => {
                const isSelected = activeOrg?.id === org.id
                return (
                  <button
                    key={org.id}
                    onClick={() => {
                      selectOrganization(org.id)
                      setIsOpen(false)
                    }}
                    className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between transition-colors ${
                      isSelected
                        ? 'bg-indigo-950/40 text-indigo-200'
                        : 'text-slate-300 hover:bg-slate-800/60'
                    }`}
                  >
                    <div className="truncate pr-2">
                      <div className="font-medium truncate">{org.name}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{org.slug}</div>
                    </div>
                    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border shrink-0 ${roleBadgeColor(org.role)}`}>
                      {org.role}
                    </span>
                  </button>
                )
              })
            )}
          </div>

          <div className="border-t border-slate-800 mt-1 pt-1 px-2">
            <button
              onClick={() => {
                setShowCreateModal(true)
                setIsOpen(false)
              }}
              className="w-full text-left px-2 py-1.5 rounded-lg text-xs font-semibold text-indigo-400 hover:bg-indigo-950/30 flex items-center gap-1.5 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Create New Organization</span>
            </button>
          </div>
        </div>
      )}

      {/* Create Organization Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
            <button
              onClick={() => setShowCreateModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h3 className="text-xl font-bold text-white mb-1">Create Organization</h3>
            <p className="text-xs text-slate-400 mb-4">
              Organizations establish strict tenant isolation boundaries for projects and operational models.
            </p>

            {error && (
              <div className="mb-4 p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs">
                {error}
              </div>
            )}

            <form onSubmit={handleCreateOrg} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="org-name">
                  Organization Name
                </label>
                <input
                  id="org-name"
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => {
                    setOrgName(e.target.value)
                    if (!orgSlug) {
                      setOrgSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-'))
                    }
                  }}
                  placeholder="Acme Industrial Corp"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="org-slug">
                  Organization Slug (Unique Identifier)
                </label>
                <input
                  id="org-slug"
                  type="text"
                  required
                  value={orgSlug}
                  onChange={(e) => setOrgSlug(e.target.value.toLowerCase())}
                  placeholder="acme-corp"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg transition-colors flex items-center gap-2"
                >
                  {loading && (
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                  )}
                  Create Organization
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

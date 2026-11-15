import { useState, useEffect, useCallback } from 'react'
import { Header } from './components/Header'
import { StatusCard } from './components/StatusCard'
import { DualModeInfo } from './components/DualModeInfo'
import { RoadmapPreview } from './components/RoadmapPreview'
import { ErrorBoundary } from './components/ErrorBoundary'
import { AuthModal } from './components/AuthModal'
import { ProjectWorkspace } from './components/ProjectWorkspace'
import { AuthProvider, useAuth } from './context/AuthContext'
import { fetchSystemHealth } from './services/api'
import type { SystemHealthResponse } from './types/api'

function AppContent() {
  const { user } = useAuth()
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authModalMode, setAuthModalMode] = useState<'login' | 'register'>('login')

  const loadHealth = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchSystemHealth()
      setHealth(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHealth()
    const intervalId = setInterval(loadHealth, 30000)
    return () => clearInterval(intervalId)
  }, [loadHealth])

  const handleOpenAuth = (mode: 'login' | 'register') => {
    setAuthModalMode(mode)
    setAuthModalOpen(true)
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      <Header health={health} loading={loading} onOpenAuth={handleOpenAuth} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 space-y-8">
        {/* Welcome Banner */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-indigo-950/60 via-slate-900 to-slate-950 border border-slate-800 p-8 shadow-2xl">
          <div className="relative z-10 max-w-3xl">
            <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400 bg-indigo-500/10 px-3 py-1 rounded-full border border-indigo-500/20">
              Phase 2 Multi-Tenancy & Authorization Active
            </span>
            <h2 className="text-3xl font-extrabold tracking-tight text-white mt-3 mb-2">
              Discover Context. Understand Operations.
            </h2>
            <p className="text-slate-400 text-sm leading-relaxed">
              Corbel is an Enterprise AI and Operational Intelligence platform. Phase 2 introduces secure user authentication, deterministic organization and membership RBAC, strict tenant isolation boundaries, and project workspace management.
            </p>
          </div>
          <div className="absolute -right-20 -bottom-20 w-80 h-80 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />
        </div>

        {/* Tenant Workspace (if logged in) or Login Prompt */}
        {user ? (
          <ProjectWorkspace />
        ) : (
          <div className="p-8 rounded-2xl bg-slate-900 border border-slate-800 text-center space-y-4">
            <div className="w-12 h-12 mx-auto rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Multi-Tenant Workspaces Require Authentication</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto mt-1">
                Sign in to your account or register a new user to create organizations, switch tenant contexts, and access tenant-scoped projects.
              </p>
            </div>
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                onClick={() => handleOpenAuth('login')}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                Sign In
              </button>
              <button
                onClick={() => handleOpenAuth('register')}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
              >
                Create Account
              </button>
            </div>
          </div>
        )}

        {/* Infrastructure Health Status */}
        <StatusCard health={health} loading={loading} onRefresh={loadHealth} />

        {/* Dual Development Environment Information */}
        <DualModeInfo />

        {/* Platform Delivery Roadmap */}
        <RoadmapPreview />
      </main>

      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
        Corbel Enterprise AI & Operational Intelligence Platform &bull; Phase 2 Active &bull; Internal Development
      </footer>

      {/* Auth Modal */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        initialMode={authModalMode}
      />
    </div>
  )
}

export function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ErrorBoundary>
  )
}

export default App

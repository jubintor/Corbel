import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'

interface AuthModalProps {
  isOpen: boolean
  onClose: () => void
  initialMode?: 'login' | 'register'
}

export function AuthModal({ isOpen, onClose, initialMode = 'login' }: AuthModalProps) {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        if (!fullName.trim()) {
          setError('Full name is required')
          setLoading(false)
          return
        }
        if (password.length < 8) {
          setError('Password must be at least 8 characters')
          setLoading(false)
          return
        }
        await register(email, password, fullName)
      }
      onClose()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('An unexpected error occurred')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden p-6 text-slate-100">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          aria-label="Close"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Tab Switcher */}
        <div className="flex border-b border-slate-800 mb-6">
          <button
            type="button"
            onClick={() => { setMode('login'); setError(null) }}
            className={`pb-3 text-sm font-semibold flex-1 text-center transition-colors border-b-2 ${
              mode === 'login'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setMode('register'); setError(null) }}
            className={`pb-3 text-sm font-semibold flex-1 text-center transition-colors border-b-2 ${
              mode === 'register'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Create Account
          </button>
        </div>

        {/* Header */}
        <div className="mb-6">
          <h3 className="text-xl font-bold text-white">
            {mode === 'login' ? 'Welcome back to Corbel' : 'Create your Corbel account'}
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            {mode === 'login'
              ? 'Enter your credentials to access tenant organizations and workspaces.'
              : 'Register to initiate tenant environments and access operational intelligence.'}
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs flex items-start gap-2">
            <svg className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="auth-fullname">
                Full Name
              </label>
              <input
                id="auth-fullname"
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Jane Doe"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="auth-email">
              Email Address
            </label>
            <input
              id="auth-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@enterprise.com"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="auth-password">
              Password {mode === 'register' && <span className="text-slate-500">(min. 8 characters)</span>}
            </label>
            <input
              id="auth-password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900/50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-lg transition-colors shadow-lg shadow-indigo-600/20 mt-2 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                <span>Processing...</span>
              </>
            ) : mode === 'login' ? (
              'Sign In'
            ) : (
              'Create Account'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

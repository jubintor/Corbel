import React from 'react'
import { Activity, Cpu, LogOut, User as UserIcon } from 'lucide-react'
import type { SystemHealthResponse } from '../types/api'
import { useAuth } from '../context/AuthContext'
import { OrgSelector } from './OrgSelector'

interface HeaderProps {
  health: SystemHealthResponse | null
  loading: boolean
  onOpenAuth: (mode: 'login' | 'register') => void
}

export const Header: React.FC<HeaderProps> = ({ health, loading, onOpenAuth }) => {
  const { user, logout } = useAuth()
  const isHealthy = health?.status === 'healthy'
  const isDbConnected = health?.database.status === 'connected'

  return (
    <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-4">
        {/* Brand identity */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white">Corbel</h1>
              <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Phase 2 Multi-Tenant
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">Enterprise AI & Operational Intelligence Platform</p>
          </div>
        </div>

        {/* Center: Org Selector if authenticated */}
        {user && (
          <div className="hidden md:flex items-center">
            <OrgSelector />
          </div>
        )}

        {/* Right Actions & Status */}
        <div className="flex items-center gap-3">
          {/* Health Badge */}
          <div
            className={`hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
              loading
                ? 'bg-slate-800/80 border-slate-700 text-slate-400'
                : isHealthy && isDbConnected
                ? 'bg-emerald-950/60 border-emerald-500/30 text-emerald-300'
                : 'bg-rose-950/60 border-rose-500/30 text-rose-300'
            }`}
          >
            <Activity
              className={`w-3 h-3 ${
                loading ? 'animate-spin' : isHealthy && isDbConnected ? 'text-emerald-400' : 'text-rose-400'
              }`}
            />
            <span className="text-[11px]">
              {loading
                ? 'Connecting...'
                : isHealthy && isDbConnected
                ? 'Stack Healthy'
                : 'Service Alert'}
            </span>
          </div>

          {/* User Controls */}
          {user ? (
            <div className="flex items-center gap-3 pl-2 border-l border-slate-800">
              <div className="flex items-center gap-2 text-xs">
                <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
                  <UserIcon className="w-3.5 h-3.5" />
                </div>
                <div className="hidden sm:block text-left">
                  <div className="text-white font-medium text-xs leading-none truncate max-w-[120px]">
                    {user.full_name}
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono leading-tight truncate max-w-[120px]">
                    {user.email}
                  </div>
                </div>
              </div>

              <button
                onClick={() => logout()}
                className="p-1.5 text-slate-400 hover:text-rose-300 hover:bg-slate-800/60 rounded-lg transition-colors"
                title="Sign Out"
                aria-label="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => onOpenAuth('login')}
                className="px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-lg transition-colors"
              >
                Sign In
              </button>
              <button
                onClick={() => onOpenAuth('register')}
                className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
              >
                Register
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Mobile Org Selector row */}
      {user && (
        <div className="md:hidden px-6 py-2 border-t border-slate-800/50 bg-slate-950/40 flex justify-center">
          <OrgSelector />
        </div>
      )}
    </header>
  )
}

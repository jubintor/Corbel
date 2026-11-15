import React from 'react'
import { Laptop, Container, Terminal } from 'lucide-react'

export const DualModeInfo: React.FC = () => {
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Terminal className="w-5 h-5 text-indigo-400" />
          Authoritative Dual Local Development Modes
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Standardized operational workflows as defined in ADR-006 and the Corbel Architecture Specification
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Mode A: Lightweight */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="flex items-center gap-2 text-sm font-semibold text-white">
                <Laptop className="w-4 h-4 text-emerald-400" />
                Mode A — Lightweight Local Dev
              </span>
              <span className="text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                Primary Everyday Workflow
              </span>
            </div>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              PostgreSQL runs in Docker. FastAPI and Vite/React run natively on the host with hot reload and instant IDE step-through debugging.
            </p>

            <div className="space-y-2 font-mono text-xs">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                <span className="text-slate-500 block text-[10px] uppercase font-sans mb-1 font-semibold">1. Start PostgreSQL (Docker)</span>
                <span className="text-indigo-300">docker compose up -d corbel-db</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                <span className="text-slate-500 block text-[10px] uppercase font-sans mb-1 font-semibold">2. Start Backend (Native)</span>
                <span className="text-indigo-300">uvicorn corbel.main:app --reload --port 8000</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                <span className="text-slate-500 block text-[10px] uppercase font-sans mb-1 font-semibold">3. Start Frontend (Native)</span>
                <span className="text-indigo-300">npm run dev</span>
              </div>
            </div>
          </div>
        </div>

        {/* Mode B: Full Containerized */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="flex items-center gap-2 text-sm font-semibold text-white">
                <Container className="w-4 h-4 text-indigo-400" />
                Mode B — Full Containerized Dev
              </span>
              <span className="text-[10px] font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded-full">
                CI / Integration Mode
              </span>
            </div>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              PostgreSQL, FastAPI backend, and React/Nginx frontend all build and run together in Docker Compose on a dedicated internal network.
            </p>

            <div className="space-y-2 font-mono text-xs">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                <span className="text-slate-500 block text-[10px] uppercase font-sans mb-1 font-semibold">Start Complete Container Stack</span>
                <span className="text-indigo-300">docker compose up --build</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                <span className="text-slate-500 block text-[10px] uppercase font-sans mb-1 font-semibold">Run in Background</span>
                <span className="text-indigo-300">docker compose up -d</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                <span className="text-slate-500 block text-[10px] uppercase font-sans mb-1 font-semibold">Stop Environment</span>
                <span className="text-indigo-300">docker compose down</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

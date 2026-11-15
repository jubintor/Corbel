import React from 'react'
import { Milestone, CheckCircle2, Lock } from 'lucide-react'

export const RoadmapPreview: React.FC = () => {
  const roadmapSteps = [
    { phase: 'Phase 1', title: 'Application Foundation', desc: 'FastAPI, React/Vite, PostgreSQL, Alembic, Dual Dev Modes', active: true, done: true },
    { phase: 'Phase 2', title: 'Authentication & Tenancy', desc: 'Organizations, Users, Projects, Deterministic RBAC', active: false, done: false },
    { phase: 'Phase 3', title: 'Data Intelligence', desc: 'P2P Datasets, Schema Profiling, Ingestion, Task Queue Evaluation', active: false, done: false },
    { phase: 'Phase 4', title: 'Ontology Engine', desc: 'Business Objects, Properties, Relationships, Semantic Discovery', active: false, done: false },
    { phase: 'Phases 5–9', title: 'Intelligence & Governed Execution', desc: 'Process Mining, Monitors, Bounded AI Investigations, Approvals', active: false, done: false },
  ]

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Milestone className="w-5 h-5 text-indigo-400" />
          Platform Implementation Roadmap
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Progressive delivery sequence adhering strictly to <code className="text-slate-300">docs/IMPLEMENTATION_PLAN.md</code>
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {roadmapSteps.map((step) => (
          <div
            key={step.phase}
            className={`rounded-xl p-3.5 border transition-all ${
              step.active
                ? 'bg-indigo-950/40 border-indigo-500/40 shadow-lg shadow-indigo-500/5'
                : 'bg-slate-950/40 border-slate-800/60 opacity-70'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className={`text-[11px] font-bold ${step.active ? 'text-indigo-400' : 'text-slate-500'}`}>
                {step.phase}
              </span>
              {step.done ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <Lock className="w-3.5 h-3.5 text-slate-600" />
              )}
            </div>
            <h4 className="text-xs font-semibold text-slate-200 mb-1">{step.title}</h4>
            <p className="text-[11px] text-slate-400 leading-tight">{step.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

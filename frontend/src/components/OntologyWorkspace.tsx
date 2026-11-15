import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  listBusinessObjects,
  getBusinessObject,
  createBusinessObject,
  deleteBusinessObject,
  addProperty,
  deleteProperty,
  listRelationships,
  createRelationship,
  deleteRelationship,
  seedP2POntology,
  discoverSemanticMappings,
  listPropertyMappings,
  acceptMapping,
  rejectMapping,
  deletePropertyMapping,
  getOntologyGraph,
} from '../services/ontology'
import { listProjectDatasets } from '../services/datasets'
import type {
  BusinessObject,
  Relationship,
  PropertyMapping,
  SemanticDiscoveryResponse,
  OntologyGraphResponse,
} from '../types/ontology'
import type { Dataset } from '../types/dataset'
import type { Project } from '../types/auth'
import { AuthApiError } from '../services/auth'

interface OntologyWorkspaceProps {
  project: Project
  onBack: () => void
}

export function OntologyWorkspace({ project, onBack }: OntologyWorkspaceProps) {
  const { token, activeOrg } = useAuth()

  // Primary workspace tabs
  const [activeTab, setActiveTab] = useState<'entities' | 'relationships' | 'discovery' | 'mappings'>('entities')

  // Ontology entities & properties state
  const [objects, setObjects] = useState<BusinessObject[]>([])
  const [selectedObject, setSelectedObject] = useState<BusinessObject | null>(null)
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [graphSummary, setGraphSummary] = useState<OntologyGraphResponse | null>(null)
  const [mappings, setMappings] = useState<PropertyMapping[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])

  // Loading & Error states
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [seedingLoading, setSeedingLoading] = useState(false)

  // Create Business Object modal
  const [showCreateObjectModal, setShowCreateObjectModal] = useState(false)
  const [newObjName, setNewObjName] = useState('')
  const [newObjDisplayName, setNewObjDisplayName] = useState('')
  const [newObjDesc, setNewObjDesc] = useState('')
  const [createObjectLoading, setCreateObjectLoading] = useState(false)
  const [createObjectError, setCreateObjectError] = useState<string | null>(null)

  // Add Property modal
  const [showAddPropModal, setShowAddPropModal] = useState(false)
  const [newPropName, setNewPropName] = useState('')
  const [newPropDisplayName, setNewPropDisplayName] = useState('')
  const [newPropType, setNewPropType] = useState('STRING')
  const [newPropIsPk, setNewPropIsPk] = useState(false)
  const [newPropIsNullable, setNewPropIsNullable] = useState(true)
  const [newPropDesc, setNewPropDesc] = useState('')
  const [addPropLoading, setAddPropLoading] = useState(false)
  const [addPropError, setAddPropError] = useState<string | null>(null)

  // Create Relationship modal
  const [showCreateRelModal, setShowCreateRelModal] = useState(false)
  const [newRelName, setNewRelName] = useState('')
  const [newRelSourceId, setNewRelSourceId] = useState('')
  const [newRelTargetId, setNewRelTargetId] = useState('')
  const [newRelCardinality, setNewRelCardinality] = useState('ONE_TO_MANY')
  const [newRelFkProp, setNewRelFkProp] = useState('')
  const [newRelDesc, setNewRelDesc] = useState('')
  const [createRelLoading, setCreateRelLoading] = useState(false)
  const [createRelError, setCreateRelError] = useState<string | null>(null)

  // Semantic Discovery state
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('')
  const [selectedVersionId, setSelectedVersionId] = useState<string>('')
  const [selectedTargetObjectId, setSelectedTargetObjectId] = useState<string>('')
  const [discoveryLoading, setDiscoveryLoading] = useState(false)
  const [discoveryError, setDiscoveryError] = useState<string | null>(null)
  const [discoveryResult, setDiscoveryResult] = useState<SemanticDiscoveryResponse | null>(null)
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null)

  // Load all ontology data
  const loadOntologyData = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      const [fetchedObjects, fetchedRelationships, fetchedGraph, fetchedMappings, fetchedDatasets] =
        await Promise.all([
          listBusinessObjects(token, activeOrg.id, project.id),
          listRelationships(token, activeOrg.id, project.id),
          getOntologyGraph(token, activeOrg.id, project.id).catch(() => null),
          listPropertyMappings(token, activeOrg.id, project.id).catch(() => []),
          listProjectDatasets(token, activeOrg.id, project.id).catch(() => []),
        ])
      setObjects(fetchedObjects)
      setRelationships(fetchedRelationships)
      setGraphSummary(fetchedGraph)
      setMappings(fetchedMappings)
      setDatasets(fetchedDatasets)

      // Auto-select first object and load its full details with properties
      if (fetchedObjects.length > 0) {
        const firstObj = fetchedObjects[0]
        try {
          const detailed = await getBusinessObject(token, activeOrg.id, project.id, firstObj.id)
          setSelectedObject(detailed)
        } catch {
          setSelectedObject(firstObj)
        }
      } else {
        setSelectedObject(null)
      }

      // Auto-select first dataset if available
      if (fetchedDatasets.length > 0) {
        setSelectedDatasetId((prev) => {
          if (!prev) {
            const firstDs = fetchedDatasets[0]
            if (firstDs.latest_version) {
              setSelectedVersionId(firstDs.latest_version.id)
            }
            return firstDs.id
          }
          return prev
        })
      }
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Failed to load ontology models and semantic mappings')
      }
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg?.id, project.id])

  useEffect(() => {
    loadOntologyData()
  }, [loadOntologyData])

  // Refresh selected object's full detail with properties
  const refreshSelectedObject = useCallback(
    async (objectId: string) => {
      if (!token || !activeOrg) return
      try {
        const detailed = await getBusinessObject(token, activeOrg.id, project.id, objectId)
        setSelectedObject(detailed)
      } catch (err) {
        console.error('Failed to refresh object details:', err)
      }
    },
    [token, activeOrg?.id, project.id]
  )

  const handleSelectObject = async (obj: BusinessObject) => {
    setSelectedObject(obj)
    await refreshSelectedObject(obj.id)
  }

  // Handle Seed P2P Ontology
  const handleSeedP2P = async () => {
    if (!token || !activeOrg) return
    setSeedingLoading(true)
    setError(null)
    setSuccessMessage(null)
    try {
      const seeded = await seedP2POntology(token, activeOrg.id, project.id)
      setSuccessMessage(
        `Successfully initialized P2P Canonical Ontology with ${seeded.length} business objects (Supplier, PurchaseOrder, GoodsReceipt, Invoice) and verified relational links.`
      )
      await loadOntologyData()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Failed to seed P2P ontology')
      }
    } finally {
      setSeedingLoading(false)
    }
  }

  // Handle Create Business Object
  const handleCreateBusinessObject = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setCreateObjectLoading(true)
    setCreateObjectError(null)
    try {
      const created = await createBusinessObject(token, activeOrg.id, project.id, {
        name: newObjName.trim(),
        display_name: newObjDisplayName.trim() || newObjName.trim(),
        description: newObjDesc.trim() || undefined,
      })
      setShowCreateObjectModal(false)
      setNewObjName('')
      setNewObjDisplayName('')
      setNewObjDesc('')
      await loadOntologyData()
      setSelectedObject(created)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setCreateObjectError(err.message)
      } else {
        setCreateObjectError('Failed to create business object')
      }
    } finally {
      setCreateObjectLoading(false)
    }
  }

  // Handle Delete Business Object
  const handleDeleteBusinessObject = async (obj: BusinessObject) => {
    if (!token || !activeOrg) return
    if (!window.confirm(`Delete Business Object "${obj.display_name}"? All associated properties and mappings will be removed.`)) {
      return
    }
    try {
      await deleteBusinessObject(token, activeOrg.id, project.id, obj.id)
      if (selectedObject?.id === obj.id) {
        setSelectedObject(null)
      }
      await loadOntologyData()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete business object')
    }
  }

  // Handle Add Property
  const handleAddProperty = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !selectedObject) return
    setAddPropLoading(true)
    setAddPropError(null)
    try {
      await addProperty(token, activeOrg.id, project.id, selectedObject.id, {
        name: newPropName.trim(),
        display_name: newPropDisplayName.trim() || newPropName.trim(),
        data_type: newPropType,
        is_primary_key: newPropIsPk,
        is_nullable: newPropIsNullable,
        description: newPropDesc.trim() || undefined,
      })
      setShowAddPropModal(false)
      setNewPropName('')
      setNewPropDisplayName('')
      setNewPropType('STRING')
      setNewPropIsPk(false)
      setNewPropIsNullable(true)
      setNewPropDesc('')
      await refreshSelectedObject(selectedObject.id)
      await loadOntologyData()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setAddPropError(err.message)
      } else {
        setAddPropError('Failed to add property')
      }
    } finally {
      setAddPropLoading(false)
    }
  }

  // Handle Delete Property
  const handleDeleteProperty = async (propId: string, propName: string) => {
    if (!token || !activeOrg || !selectedObject) return
    if (!window.confirm(`Delete property "${propName}"? Any associated column mappings will be cleared.`)) {
      return
    }
    try {
      await deleteProperty(token, activeOrg.id, project.id, selectedObject.id, propId)
      await refreshSelectedObject(selectedObject.id)
      await loadOntologyData()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete property')
    }
  }

  // Handle Create Relationship
  const handleCreateRelationship = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setCreateRelLoading(true)
    setCreateRelError(null)
    try {
      await createRelationship(token, activeOrg.id, project.id, {
        name: newRelName.trim(),
        source_object_id: newRelSourceId,
        target_object_id: newRelTargetId,
        cardinality: newRelCardinality,
        description: newRelDesc.trim() || undefined,
        join_expression: newRelFkProp.trim() ? { foreign_key_property: newRelFkProp.trim() } : undefined,
      })
      setShowCreateRelModal(false)
      setNewRelName('')
      setNewRelSourceId('')
      setNewRelTargetId('')
      setNewRelCardinality('ONE_TO_MANY')
      setNewRelFkProp('')
      setNewRelDesc('')
      await loadOntologyData()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setCreateRelError(err.message)
      } else {
        setCreateRelError('Failed to create relationship')
      }
    } finally {
      setCreateRelLoading(false)
    }
  }

  // Handle Delete Relationship
  const handleDeleteRelationship = async (relId: string, relName: string) => {
    if (!token || !activeOrg) return
    if (!window.confirm(`Delete relationship "${relName}"?`)) {
      return
    }
    try {
      await deleteRelationship(token, activeOrg.id, project.id, relId)
      await loadOntologyData()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete relationship')
    }
  }

  // Handle Run Semantic Discovery
  const handleRunDiscovery = async () => {
    if (!token || !activeOrg || !selectedDatasetId || !selectedVersionId || !selectedTargetObjectId) {
      setDiscoveryError('Please select a dataset, dataset version, and target business object.')
      return
    }
    setDiscoveryLoading(true)
    setDiscoveryError(null)
    setDiscoveryResult(null)
    try {
      const result = await discoverSemanticMappings(token, activeOrg.id, project.id, {
        dataset_id: selectedDatasetId,
        dataset_version_id: selectedVersionId,
        business_object_id: selectedTargetObjectId,
      })
      setDiscoveryResult(result)
      await loadOntologyData()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setDiscoveryError(err.message)
      } else {
        setDiscoveryError('Semantic discovery failed')
      }
    } finally {
      setDiscoveryLoading(false)
    }
  }

  // Handle Accept Suggestion
  const handleAcceptMapping = async (mappingId: string) => {
    if (!token || !activeOrg) return
    setActionLoadingId(mappingId)
    try {
      await acceptMapping(token, activeOrg.id, project.id, mappingId)
      // Update in discoveryResult if present
      if (discoveryResult) {
        setDiscoveryResult({
          ...discoveryResult,
          suggestions: discoveryResult.suggestions.map((s) =>
            s.id === mappingId ? { ...s, status: 'CONFIRMED' } : s
          ),
        })
      }
      await loadOntologyData()
      if (selectedObject?.id) {
        await refreshSelectedObject(selectedObject.id)
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to accept mapping')
    } finally {
      setActionLoadingId(null)
    }
  }

  // Handle Reject Suggestion
  const handleRejectMapping = async (mappingId: string) => {
    if (!token || !activeOrg) return
    setActionLoadingId(mappingId)
    try {
      await rejectMapping(token, activeOrg.id, project.id, mappingId)
      if (discoveryResult) {
        setDiscoveryResult({
          ...discoveryResult,
          suggestions: discoveryResult.suggestions.map((s) =>
            s.id === mappingId ? { ...s, status: 'REJECTED' } : s
          ),
        })
      }
      await loadOntologyData()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to reject mapping')
    } finally {
      setActionLoadingId(null)
    }
  }

  // Handle Delete Confirmed Mapping
  const handleDeleteMapping = async (mappingId: string) => {
    if (!token || !activeOrg) return
    if (!window.confirm('Remove this property mapping? The ontology property will become unmapped.')) {
      return
    }
    try {
      await deletePropertyMapping(token, activeOrg.id, project.id, mappingId)
      await loadOntologyData()
      if (selectedObject?.id) {
        await refreshSelectedObject(selectedObject.id)
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to remove mapping')
    }
  }

  const renderTypeBadge = (type: string) => {
    let color = 'bg-slate-800 text-slate-300 border-slate-700'
    if (type === 'NUMBER') {
      color = 'bg-blue-500/10 text-blue-400 border-blue-500/20'
    } else if (type === 'DATETIME') {
      color = 'bg-purple-500/10 text-purple-400 border-purple-500/20'
    } else if (type === 'BOOLEAN') {
      color = 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    } else if (type === 'STRING') {
      color = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    } else if (type === 'ENUM') {
      color = 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
    }
    return (
      <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border ${color}`}>
        {type}
      </span>
    )
  }

  const renderConfidenceBadge = (confidence: number) => {
    const pct = Math.round(confidence * 100)
    let color = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    if (pct < 60) {
      color = 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    } else if (pct < 85) {
      color = 'bg-blue-500/10 text-blue-400 border-blue-500/20'
    }
    return (
      <span className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${color}`}>
        {pct}%
      </span>
    )
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Workspace Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-1 text-xs"
              title="Back to Projects"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              <span>Projects</span>
            </button>
            <span className="text-slate-600">/</span>
            <h3 className="text-lg font-bold text-white">{project.name}</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Ontology Engine & Semantic Discovery
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Define canonical business entities, typed relationships, and deterministically map tabular dataset columns to ontology properties.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleSeedP2P}
            disabled={seedingLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white text-xs font-semibold rounded-lg transition-all shadow-lg shadow-indigo-600/20 shrink-0 disabled:opacity-50"
          >
            {seedingLoading ? (
              <svg className="w-4 h-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            )}
            <span>Seed P2P Ontology</span>
          </button>
        </div>
      </div>

      {/* Notifications / Alerts */}
      {loading && (
        <div className="py-2 text-center text-xs text-indigo-400 flex items-center justify-center gap-2">
          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          <span>Loading ontology workspace...</span>
        </div>
      )}

      {successMessage && (
        <div className="p-3 bg-emerald-950/60 border border-emerald-800/80 rounded-lg text-emerald-200 text-xs flex items-center justify-between">
          <span>{successMessage}</span>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-400 hover:text-emerald-200 text-sm">
            &times;
          </button>
        </div>
      )}

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs">
          {error}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex items-center gap-1 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('entities')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'entities'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <span>Entities & Properties ({objects.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('relationships')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'relationships'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
          </svg>
          <span>Relationships & Graph ({relationships.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('discovery')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'discovery'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span>Semantic Discovery</span>
        </button>

        <button
          onClick={() => setActiveTab('mappings')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'mappings'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span>Confirmed Mappings ({mappings.filter((m) => m.status === 'CONFIRMED').length})</span>
        </button>
      </div>

      {/* Tab 1: Entities & Properties */}
      {activeTab === 'entities' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-bold text-white">Business Entities</h4>
              <p className="text-xs text-slate-400">
                Core domain concepts with structured properties, primary keys, and data types.
              </p>
            </div>
            <button
              onClick={() => setShowCreateObjectModal(true)}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>New Business Object</span>
            </button>
          </div>

          {objects.length === 0 ? (
            <div className="p-8 text-center bg-slate-950/60 border border-slate-800/80 rounded-xl space-y-3">
              <p className="text-sm text-slate-300 font-semibold">No Business Objects defined yet.</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Click &ldquo;Seed P2P Ontology&rdquo; above to automatically initialize Supplier, PurchaseOrder, GoodsReceipt, and Invoice entities.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left Column: Entity Cards */}
              <div className="space-y-3 lg:col-span-1">
                {objects.map((obj) => {
                  const isSelected = selectedObject?.id === obj.id
                  return (
                    <div
                      key={obj.id}
                      onClick={() => handleSelectObject(obj)}
                      className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-indigo-950/40 border-indigo-500/60 shadow-md shadow-indigo-500/10'
                          : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="font-bold text-sm text-white flex items-center gap-2">
                            <span>{obj.display_name}</span>
                            <span className="text-[10px] font-mono text-slate-400">({obj.name})</span>
                          </div>
                          <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                            {obj.description || 'No description provided.'}
                          </p>
                        </div>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 shrink-0">
                          {obj.property_count} props
                        </span>
                      </div>
                      <div className="mt-3 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                        <span>PK: <code className="text-indigo-300">{obj.primary_key_property || 'None'}</code></span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDeleteBusinessObject(obj)
                          }}
                          className="text-rose-400 hover:text-rose-300 text-[10px] hover:underline"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Right Column: Properties of Selected Entity */}
              <div className="lg:col-span-2 bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 space-y-4">
                {selectedObject ? (
                  <>
                    <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                      <div>
                        <div className="flex items-center gap-2">
                          <h5 className="font-bold text-white text-base">{selectedObject.display_name}</h5>
                          <span className="text-xs font-mono text-slate-500">({selectedObject.name})</span>
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {selectedObject.description || 'No description provided.'}
                        </p>
                      </div>
                      <button
                        onClick={() => setShowAddPropModal(true)}
                        className="px-3 py-1.5 bg-indigo-600/80 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                        <span>Add Property</span>
                      </button>
                    </div>

                    {(!selectedObject.properties || selectedObject.properties.length === 0) ? (
                      <div className="py-8 text-center text-xs text-slate-500">
                        No properties defined on this business entity. Add a property or seed P2P defaults.
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs border-collapse">
                          <thead>
                            <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                              <th className="py-2 px-3">Property Name</th>
                              <th className="py-2 px-3">Type</th>
                              <th className="py-2 px-3">Key & Nullable</th>
                              <th className="py-2 px-3">Source Mapping</th>
                              <th className="py-2 px-3 text-right">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {selectedObject.properties.map((p) => {
                              const isMapped = !!p.source_mapping
                              return (
                                <tr key={p.id} className="hover:bg-slate-900/40">
                                  <td className="py-2.5 px-3">
                                    <div className="font-mono text-white font-semibold">{p.name}</div>
                                    {p.display_name && p.display_name !== p.name && (
                                      <div className="text-[11px] text-slate-400">{p.display_name}</div>
                                    )}
                                    {p.description && (
                                      <div className="text-[10px] text-slate-500 mt-0.5 line-clamp-1">
                                        {p.description}
                                      </div>
                                    )}
                                  </td>
                                  <td className="py-2.5 px-3">
                                    {renderTypeBadge(p.data_type)}
                                  </td>
                                  <td className="py-2.5 px-3 space-x-1.5">
                                    {p.is_primary_key && (
                                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold">
                                        PRIMARY KEY
                                      </span>
                                    )}
                                    <span className="text-[10px] text-slate-400">
                                      {p.is_nullable ? 'Nullable' : 'Required'}
                                    </span>
                                  </td>
                                  <td className="py-2.5 px-3">
                                    {isMapped ? (
                                      <div className="space-y-0.5">
                                        <div className="flex items-center gap-1.5">
                                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                          <span className="font-mono text-emerald-300 font-semibold">
                                            {p.source_mapping?.column_name}
                                          </span>
                                        </div>
                                        <div className="text-[10px] text-slate-500">
                                          Confidence: {Math.round((p.source_mapping?.confidence || 0) * 100)}%
                                        </div>
                                      </div>
                                    ) : (
                                      <span className="text-[11px] text-slate-500 italic">Unmapped</span>
                                    )}
                                  </td>
                                  <td className="py-2.5 px-3 text-right">
                                    <button
                                      onClick={() => handleDeleteProperty(p.id, p.name)}
                                      className="text-slate-500 hover:text-rose-400 text-xs transition-colors"
                                      title="Delete property"
                                    >
                                      Delete
                                    </button>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="py-12 text-center text-xs text-slate-500">
                    Select a business object from the left panel to inspect its properties.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Relationships & Graph */}
      {activeTab === 'relationships' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-bold text-white">Typed Relationships & Knowledge Graph</h4>
              <p className="text-xs text-slate-400">
                Directed relational connections between business entities with strict referential consistency.
              </p>
            </div>
            <button
              onClick={() => {
                if (objects.length < 2) {
                  alert('At least two Business Objects are required to create a relationship.')
                  return
                }
                setNewRelSourceId(objects[0]?.id || '')
                setNewRelTargetId(objects[1]?.id || '')
                setShowCreateRelModal(true)
              }}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>New Relationship</span>
            </button>
          </div>

          {/* Graph Metrics Card */}
          {graphSummary && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl">
                <div className="text-[11px] text-slate-400">Entities in Graph</div>
                <div className="text-xl font-bold text-white mt-1">{graphSummary.total_objects}</div>
              </div>
              <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl">
                <div className="text-[11px] text-slate-400">Relational Links</div>
                <div className="text-xl font-bold text-indigo-400 mt-1">{graphSummary.total_relationships}</div>
              </div>
              <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl">
                <div className="text-[11px] text-slate-400">Mapped Properties</div>
                <div className="text-xl font-bold text-emerald-400 mt-1">{graphSummary.total_mapped_properties}</div>
              </div>
            </div>
          )}

          {/* Relationships List */}
          {relationships.length === 0 ? (
            <div className="p-8 text-center bg-slate-950/60 border border-slate-800/80 rounded-xl space-y-3">
              <p className="text-sm text-slate-300 font-semibold">No relationships defined yet.</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Seed the P2P ontology to automatically link Supplier &rarr; PurchaseOrder &rarr; GoodsReceipt &rarr; Invoice.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {relationships.map((rel) => (
                <div
                  key={rel.id}
                  className="p-4 bg-slate-950/60 border border-slate-800/80 rounded-xl flex flex-col justify-between space-y-3"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm font-bold text-white">
                        <span className="text-indigo-300">{rel.source_object_name || 'Source'}</span>
                        <span className="text-slate-600">&rarr;</span>
                        <span className="text-indigo-300">{rel.target_object_name || 'Target'}</span>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                        {rel.cardinality}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-300 font-mono">
                      relation: <span className="font-semibold text-white">{rel.name}</span>
                    </div>
                    {rel.description && (
                      <p className="text-xs text-slate-400 mt-1.5">{rel.description}</p>
                    )}
                    {rel.join_expression && (
                      <div className="mt-2 text-[11px] font-mono text-slate-400 bg-slate-900/60 p-1.5 rounded border border-slate-800/60">
                        Join Key: {JSON.stringify(rel.join_expression)}
                      </div>
                    )}
                  </div>
                  <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                    <span>Created {new Date(rel.created_at).toLocaleDateString()}</span>
                    <button
                      onClick={() => handleDeleteRelationship(rel.id, rel.name)}
                      className="text-rose-400 hover:text-rose-300 hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Semantic Discovery */}
      {activeTab === 'discovery' && (
        <div className="space-y-6">
          {/* Deterministic Discovery Notice */}
          <div className="p-4 bg-indigo-950/30 border border-indigo-500/30 rounded-xl space-y-1.5 text-xs">
            <div className="flex items-center gap-2 text-indigo-300 font-bold">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Deterministic Semantic Discovery & Human Approval Gate</span>
            </div>
            <p className="text-slate-300">
              Candidate suggestions are generated deterministically by evaluating column names, P2P canonical aliases, data types, and profile distributions (cardinality, uniqueness, and null ratios).
            </p>
            <p className="text-slate-400 font-semibold">
              Crucial Governance Rule: Suggestions remain unconfirmed until explicitly accepted by a human operator.
            </p>
          </div>

          {/* Discovery Controls */}
          <div className="p-4 bg-slate-950/60 border border-slate-800/80 rounded-xl space-y-4">
            <h5 className="font-bold text-white text-xs uppercase tracking-wider">Configure Discovery Run</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Source Dataset</label>
                <select
                  value={selectedDatasetId}
                  onChange={(e) => {
                    const dsId = e.target.value
                    setSelectedDatasetId(dsId)
                    const ds = datasets.find((d) => d.id === dsId)
                    if (ds?.latest_version) {
                      setSelectedVersionId(ds.latest_version.id)
                    } else {
                      setSelectedVersionId('')
                    }
                  }}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">-- Select Ingested Dataset --</option>
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} {d.latest_version?.file_format ? `(${d.latest_version.file_format})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Target Business Object</label>
                <select
                  value={selectedTargetObjectId}
                  onChange={(e) => setSelectedTargetObjectId(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">-- Select Target Entity --</option>
                  {objects.map((obj) => (
                    <option key={obj.id} value={obj.id}>
                      {obj.display_name} ({obj.name})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-end">
                <button
                  onClick={handleRunDiscovery}
                  disabled={discoveryLoading || !selectedDatasetId || !selectedTargetObjectId}
                  className="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {discoveryLoading ? (
                    <>
                      <svg className="w-4 h-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                      </svg>
                      <span>Running Matcher...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                      <span>Discover Candidate Mappings</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {discoveryError && (
              <div className="p-2.5 bg-rose-950/60 border border-rose-800/80 rounded text-rose-200 text-xs">
                {discoveryError}
              </div>
            )}
          </div>

          {/* Discovery Results */}
          {discoveryResult && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h5 className="font-bold text-white text-sm">
                  Candidate Mapping Suggestions for <span className="text-indigo-400">{discoveryResult.business_object_name}</span>
                </h5>
                <span className="text-xs font-mono text-slate-400">
                  {discoveryResult.total_suggested} candidate(s) discovered
                </span>
              </div>

              {discoveryResult.suggestions.length === 0 ? (
                <div className="p-8 text-center bg-slate-950/60 border border-slate-800/80 rounded-xl text-xs text-slate-400">
                  No compatible candidate suggestions found between the selected dataset version and {discoveryResult.business_object_name}.
                </div>
              ) : (
                <div className="overflow-x-auto bg-slate-950/60 border border-slate-800/80 rounded-xl">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 font-semibold bg-slate-900/40">
                        <th className="py-2.5 px-3">Source Column</th>
                        <th className="py-2.5 px-3">Target Property</th>
                        <th className="py-2.5 px-3">Confidence</th>
                        <th className="py-2.5 px-3">Matching Rationale</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3 text-right">Human Gate Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {discoveryResult.suggestions.map((s) => {
                        const isActionLoading = actionLoadingId === s.id
                        return (
                          <tr key={s.id} className="hover:bg-slate-900/40">
                            <td className="py-3 px-3 font-mono text-white font-semibold">
                              {s.column_name}
                            </td>
                            <td className="py-3 px-3">
                              <span className="font-mono text-indigo-300 font-bold">{s.property_name}</span>
                            </td>
                            <td className="py-3 px-3">
                              {renderConfidenceBadge(s.confidence)}
                            </td>
                            <td className="py-3 px-3 text-slate-300 text-[11px] max-w-xs">
                              {s.explanation || 'Semantic alias & type compatibility match'}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                                  s.status === 'CONFIRMED'
                                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                    : s.status === 'REJECTED'
                                    ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                                    : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                }`}
                              >
                                {s.status}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-right space-x-2">
                              {s.status === 'SUGGESTED' ? (
                                <>
                                  <button
                                    onClick={() => handleAcceptMapping(s.id)}
                                    disabled={isActionLoading}
                                    className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded text-[11px] transition-colors disabled:opacity-50"
                                  >
                                    Accept
                                  </button>
                                  <button
                                    onClick={() => handleRejectMapping(s.id)}
                                    disabled={isActionLoading}
                                    className="px-2.5 py-1 bg-slate-800 hover:bg-rose-900/60 text-slate-300 hover:text-rose-200 font-semibold rounded text-[11px] transition-colors disabled:opacity-50"
                                  >
                                    Reject
                                  </button>
                                </>
                              ) : (
                                <span className="text-[11px] text-slate-500 italic">
                                  {s.status === 'CONFIRMED' ? 'Approved & Active' : 'Dismissed'}
                                </span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Confirmed Mappings */}
      {activeTab === 'mappings' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-bold text-white">Confirmed Column-to-Property Mappings</h4>
              <p className="text-xs text-slate-400">
                Active connections binding ingested tabular dataset columns to canonical business ontology properties.
              </p>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Total Active: {mappings.filter((m) => m.status === 'CONFIRMED').length}
            </span>
          </div>

          {mappings.filter((m) => m.status === 'CONFIRMED').length === 0 ? (
            <div className="p-8 text-center bg-slate-950/60 border border-slate-800/80 rounded-xl space-y-2">
              <p className="text-sm text-slate-300 font-semibold">No confirmed mappings yet.</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Run Semantic Discovery and accept candidate suggestions to connect dataset columns to your business ontology.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto bg-slate-950/60 border border-slate-800/80 rounded-xl">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-semibold bg-slate-900/40">
                    <th className="py-2.5 px-3">Dataset Column</th>
                    <th className="py-2.5 px-3">Ontology Target</th>
                    <th className="py-2.5 px-3">Confidence</th>
                    <th className="py-2.5 px-3">Mapped At</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {mappings
                    .filter((m) => m.status === 'CONFIRMED')
                    .map((m) => (
                      <tr key={m.id} className="hover:bg-slate-900/40">
                        <td className="py-3 px-3">
                          <div className="font-mono text-white font-semibold">{m.column_name}</div>
                          <div className="text-[10px] text-slate-500 font-mono">
                            Dataset ID: {m.dataset_id.slice(0, 8)}...
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          <div className="font-bold text-indigo-300 font-mono">{m.property_name}</div>
                          <div className="text-[10px] text-slate-400">
                            Object: {m.business_object_name || m.business_object_id || 'Canonical'}
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          {renderConfidenceBadge(m.confidence)}
                        </td>
                        <td className="py-3 px-3 text-slate-400 text-[11px]">
                          {new Date(m.created_at).toLocaleString()}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <button
                            onClick={() => handleDeleteMapping(m.id)}
                            className="text-rose-400 hover:text-rose-300 text-xs hover:underline"
                          >
                            Unmap
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modal: Create Business Object */}
      {showCreateObjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h4 className="font-bold text-white text-base">New Business Object</h4>
              <button
                onClick={() => setShowCreateObjectModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateBusinessObject} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Entity Name (Identifier)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Supplier, PurchaseOrder, PaymentReceipt"
                  value={newObjName}
                  onChange={(e) => setNewObjName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Display Name</label>
                <input
                  type="text"
                  placeholder="e.g. Purchase Order"
                  value={newObjDisplayName}
                  onChange={(e) => setNewObjDisplayName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Describe the business concept and operational role..."
                  value={newObjDesc}
                  onChange={(e) => setNewObjDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {createObjectError && (
                <div className="p-2.5 bg-rose-950/60 border border-rose-800/80 rounded text-rose-200 text-xs">
                  {createObjectError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateObjectModal(false)}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createObjectLoading}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-lg transition-colors disabled:opacity-50"
                >
                  {createObjectLoading ? 'Creating...' : 'Create Entity'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Add Property */}
      {showAddPropModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h4 className="font-bold text-white text-base">Add Property to {selectedObject?.display_name}</h4>
              <button
                onClick={() => setShowAddPropModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleAddProperty} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Property Name (Identifier)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. order_number, total_amount, created_date"
                  value={newPropName}
                  onChange={(e) => setNewPropName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Display Name</label>
                <input
                  type="text"
                  placeholder="e.g. Order Number"
                  value={newPropDisplayName}
                  onChange={(e) => setNewPropDisplayName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Data Type</label>
                  <select
                    value={newPropType}
                    onChange={(e) => setNewPropType(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
                  >
                    <option value="STRING">STRING</option>
                    <option value="NUMBER">NUMBER</option>
                    <option value="DATETIME">DATETIME</option>
                    <option value="BOOLEAN">BOOLEAN</option>
                    <option value="ENUM">ENUM</option>
                  </select>
                </div>

                <div className="flex flex-col justify-end space-y-2 pb-1">
                  <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={newPropIsPk}
                      onChange={(e) => setNewPropIsPk(e.target.checked)}
                      className="rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>Primary Key</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={newPropIsNullable}
                      onChange={(e) => setNewPropIsNullable(e.target.checked)}
                      className="rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>Nullable</span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Detailed business description..."
                  value={newPropDesc}
                  onChange={(e) => setNewPropDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {addPropError && (
                <div className="p-2.5 bg-rose-950/60 border border-rose-800/80 rounded text-rose-200 text-xs">
                  {addPropError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddPropModal(false)}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addPropLoading}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-lg transition-colors disabled:opacity-50"
                >
                  {addPropLoading ? 'Adding...' : 'Add Property'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Create Relationship */}
      {showCreateRelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h4 className="font-bold text-white text-base">New Relationship</h4>
              <button
                onClick={() => setShowCreateRelModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateRelationship} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Source Entity</label>
                  <select
                    value={newRelSourceId}
                    onChange={(e) => setNewRelSourceId(e.target.value)}
                    required
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                  >
                    {objects.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.display_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Target Entity</label>
                  <select
                    value={newRelTargetId}
                    onChange={(e) => setNewRelTargetId(e.target.value)}
                    required
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                  >
                    {objects.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.display_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Relationship Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. supplies, billed_in, received_as"
                  value={newRelName}
                  onChange={(e) => setNewRelName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Cardinality</label>
                  <select
                    value={newRelCardinality}
                    onChange={(e) => setNewRelCardinality(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
                  >
                    <option value="ONE_TO_ONE">ONE_TO_ONE</option>
                    <option value="ONE_TO_MANY">ONE_TO_MANY</option>
                    <option value="MANY_TO_ONE">MANY_TO_ONE</option>
                    <option value="MANY_TO_MANY">MANY_TO_MANY</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Foreign Key Property</label>
                  <input
                    type="text"
                    placeholder="e.g. supplier_id, po_number"
                    value={newRelFkProp}
                    onChange={(e) => setNewRelFkProp(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Explain operational meaning of connection..."
                  value={newRelDesc}
                  onChange={(e) => setNewRelDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-white text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {createRelError && (
                <div className="p-2.5 bg-rose-950/60 border border-rose-800/80 rounded text-rose-200 text-xs">
                  {createRelError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateRelModal(false)}
                  className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createRelLoading}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-lg transition-colors disabled:opacity-50"
                >
                  {createRelLoading ? 'Creating...' : 'Create Relationship'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

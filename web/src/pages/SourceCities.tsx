import { useEffect, useState } from 'react'
import { ALL_SOURCES, SOURCE_COLORS } from '../lib/constants'

interface SourceEntry {
  is_supported: boolean
  source_config: Record<string, unknown>
}

interface CityData {
  city_name: string
  city_key: string
  sources: Record<string, SourceEntry>
}

interface StateGroup {
  state_name: string
  state_key: string
  cities: CityData[]
}

interface EditTarget {
  city_key: string
  source: string
  is_supported: boolean
  config_text: string
}

const API = '/api/source-cities'

function toKey(name: string) {
  return name.toLowerCase().replace(/\s+/g, '-')
}

export default function SourceCities() {
  const [groups, setGroups] = useState<StateGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedStates, setExpandedStates] = useState<Set<string>>(new Set(['tamil-nadu']))
  const [edit, setEdit] = useState<EditTarget | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [addCityFor, setAddCityFor] = useState<{ state_name: string; state_key: string } | null>(null)
  const [newCityName, setNewCityName] = useState('')

  const [addStateOpen, setAddStateOpen] = useState(false)
  const [newStateName, setNewStateName] = useState('')
  const [newStateFirstCity, setNewStateFirstCity] = useState('')

  const [runningState, setRunningState] = useState<string | null>(null)
  const [runResult, setRunResult] = useState<Record<string, number | 'error'>>({})

  async function runState(state_key: string) {
    setRunningState(state_key)
    try {
      const res = await fetch(`/api/scrape/state/${state_key}`, { method: 'POST' })
      const data = await res.json()
      setRunResult(prev => ({ ...prev, [state_key]: data.triggered ?? 0 }))
    } catch {
      setRunResult(prev => ({ ...prev, [state_key]: 'error' }))
    }
    setRunningState(null)
  }

  async function fetchGroups() {
    setLoading(true)
    const res = await fetch(`${API}/`)
    const data = await res.json()
    setGroups(data)
    setLoading(false)
  }

  useEffect(() => { fetchGroups() }, [])

  function toggleState(state_key: string) {
    setExpandedStates(prev => {
      const next = new Set(prev)
      next.has(state_key) ? next.delete(state_key) : next.add(state_key)
      return next
    })
  }

  function openEdit(city_key: string, source: string, entry: SourceEntry) {
    if (edit?.city_key === city_key && edit?.source === source) {
      setEdit(null)
      setEditError(null)
      return
    }
    setEdit({
      city_key,
      source,
      is_supported: entry.is_supported,
      config_text: JSON.stringify(entry.source_config, null, 2),
    })
    setEditError(null)
  }

  async function saveEdit() {
    if (!edit) return
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(edit.config_text || '{}')
    } catch {
      setEditError('Invalid JSON')
      return
    }
    setSaving(true)
    await fetch(`${API}/${edit.city_key}/${edit.source}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_supported: edit.is_supported, source_config: parsed }),
    })
    setSaving(false)
    setEdit(null)
    setEditError(null)
    await fetchGroups()
  }

  async function addCity() {
    if (!addCityFor || !newCityName.trim()) return
    const city_key = toKey(newCityName.trim())
    await fetch(`${API}/cities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state_name: addCityFor.state_name,
        state_key: addCityFor.state_key,
        city_name: newCityName.trim(),
        city_key,
      }),
    })
    setAddCityFor(null)
    setNewCityName('')
    await fetchGroups()
  }

  async function addState() {
    if (!newStateName.trim() || !newStateFirstCity.trim()) return
    const state_key = toKey(newStateName.trim())
    const city_key = toKey(newStateFirstCity.trim())
    await fetch(`${API}/cities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        state_name: newStateName.trim(),
        state_key,
        city_name: newStateFirstCity.trim(),
        city_key,
      }),
    })
    setAddStateOpen(false)
    setNewStateName('')
    setNewStateFirstCity('')
    setExpandedStates(prev => new Set([...prev, state_key]))
    await fetchGroups()
  }

  async function deleteCity(city_key: string) {
    if (!confirm(`Remove ${city_key} and all its source configs?`)) return
    await fetch(`${API}/cities/${city_key}`, { method: 'DELETE' })
    if (edit?.city_key === city_key) setEdit(null)
    await fetchGroups()
  }

  if (loading) {
    return <div className="text-slate-500 text-sm py-12 text-center">Loading city configs…</div>
  }

  return (
    <div className="max-w-5xl mx-auto space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-slate-100 font-semibold">States &amp; Source Config</h2>
          <p className="text-slate-500 text-xs mt-0.5">
            Enable cities per scraper source. Changes take effect on the next scrape run.
          </p>
        </div>
        <button
          onClick={fetchGroups}
          className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 px-3 py-1.5 rounded transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Source legend */}
      <div className="flex gap-4 px-4 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs">
        {ALL_SOURCES.map(src => (
          <span key={src} className={`font-mono ${SOURCE_COLORS[src]}`}>{src}</span>
        ))}
      </div>

      {/* State accordions */}
      {groups.map(group => (
        <div key={group.state_key} className="border border-slate-800 rounded-lg overflow-hidden">
          {/* State header */}
          <div
            className="w-full flex items-center justify-between px-4 py-3 bg-slate-900 hover:bg-slate-800 transition-colors cursor-pointer"
            onClick={() => toggleState(group.state_key)}
          >
            <div className="flex items-center gap-3">
              <span className={`text-xs transition-transform ${expandedStates.has(group.state_key) ? 'rotate-90' : ''}`}>▶</span>
              <span className="text-slate-200 font-medium">{group.state_name}</span>
              <span className="text-slate-600 text-xs">{group.cities.length} cities</span>
              {runResult[group.state_key] !== undefined && (
                <span className={`text-xs ${runResult[group.state_key] === 'error' ? 'text-red-400' : 'text-emerald-400'}`}>
                  {runResult[group.state_key] === 'error'
                    ? 'error'
                    : runResult[group.state_key] === 0
                      ? 'no active configs'
                      : `${runResult[group.state_key]} config(s) running`}
                </span>
              )}
            </div>
            <button
              onClick={e => { e.stopPropagation(); runState(group.state_key) }}
              disabled={runningState === group.state_key}
              className="text-xs text-slate-500 hover:text-slate-200 px-2 py-0.5 rounded hover:bg-slate-700 disabled:opacity-40 transition-colors"
              title="Run all active configs for this state"
            >
              {runningState === group.state_key ? '…' : '▶ Run'}
            </button>
          </div>

          {expandedStates.has(group.state_key) && (
            <div className="divide-y divide-slate-800/50">
              {group.cities.map(city => (
                <div key={city.city_key}>
                  {/* City row */}
                  <div className="flex items-center gap-2 px-4 py-2.5 bg-[#0f1117] hover:bg-slate-950">
                    <span className="text-slate-300 text-sm w-36 shrink-0">{city.city_name}</span>
                    <div className="flex gap-1.5 flex-wrap flex-1">
                      {ALL_SOURCES.map(src => {
                        const entry = city.sources[src] ?? { is_supported: false, source_config: {} }
                        const active = edit?.city_key === city.city_key && edit?.source === src
                        return (
                          <button
                            key={src}
                            onClick={() => openEdit(city.city_key, src, entry)}
                            title={`Edit ${src} config for ${city.city_name}`}
                            className={`font-mono text-xs px-2 py-0.5 rounded border transition-colors ${
                              active
                                ? 'border-slate-500 bg-slate-700 ' + SOURCE_COLORS[src]
                                : entry.is_supported
                                  ? 'border-slate-700 bg-slate-900 ' + SOURCE_COLORS[src]
                                  : 'border-slate-800 bg-slate-950 text-slate-600'
                            }`}
                          >
                            {src}
                          </button>
                        )
                      })}
                    </div>
                    <button
                      onClick={() => deleteCity(city.city_key)}
                      className="text-slate-700 hover:text-red-400 text-xs ml-2 transition-colors shrink-0"
                      title="Remove city"
                    >
                      ✕
                    </button>
                  </div>

                  {/* Inline source editor */}
                  {edit?.city_key === city.city_key && (
                    <div className="px-4 py-3 bg-slate-900 border-t border-slate-800">
                      <div className="flex items-center gap-4 mb-3">
                        <span className={`font-mono text-sm font-medium ${SOURCE_COLORS[edit.source]}`}>{edit.source}</span>
                        <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={edit.is_supported}
                            onChange={e => setEdit({ ...edit, is_supported: e.target.checked })}
                            className="accent-green-500"
                          />
                          Supported
                        </label>
                      </div>
                      <div className="mb-2">
                        <div className="text-xs text-slate-500 mb-1">source_config (JSON)</div>
                        <textarea
                          value={edit.config_text}
                          onChange={e => {
                            setEdit({ ...edit, config_text: e.target.value })
                            setEditError(null)
                          }}
                          rows={4}
                          spellCheck={false}
                          className={`w-full font-mono text-xs bg-slate-950 text-slate-300 border rounded px-3 py-2 resize-none outline-none focus:border-slate-500 ${
                            editError ? 'border-red-600' : 'border-slate-700'
                          }`}
                        />
                        {editError && <div className="text-red-400 text-xs mt-1">{editError}</div>}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={saveEdit}
                          disabled={saving}
                          className="px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-100 rounded transition-colors disabled:opacity-50"
                        >
                          {saving ? 'Saving…' : 'Save'}
                        </button>
                        <button
                          onClick={() => { setEdit(null); setEditError(null) }}
                          className="px-3 py-1 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Add city row */}
              <div className="px-4 py-2 bg-[#0f1117]">
                {addCityFor?.state_key === group.state_key ? (
                  <div className="flex items-center gap-2">
                    <input
                      autoFocus
                      value={newCityName}
                      onChange={e => setNewCityName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') addCity(); if (e.key === 'Escape') { setAddCityFor(null); setNewCityName('') } }}
                      placeholder="City name"
                      className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm text-slate-200 outline-none focus:border-slate-500 w-48"
                    />
                    <span className="text-slate-600 text-xs font-mono">→ {toKey(newCityName) || 'city-key'}</span>
                    <button onClick={addCity} className="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 rounded transition-colors">Add</button>
                    <button onClick={() => { setAddCityFor(null); setNewCityName('') }} className="text-xs text-slate-500 hover:text-slate-300">Cancel</button>
                  </div>
                ) : (
                  <button
                    onClick={() => setAddCityFor({ state_name: group.state_name, state_key: group.state_key })}
                    className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
                  >
                    + Add city
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Add state */}
      <div className="border border-dashed border-slate-800 rounded-lg">
        {addStateOpen ? (
          <div className="px-4 py-3 space-y-2">
            <div className="text-xs text-slate-500 font-medium">New State</div>
            <div className="flex gap-2">
              <div>
                <input
                  autoFocus
                  value={newStateName}
                  onChange={e => setNewStateName(e.target.value)}
                  placeholder="State name"
                  className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm text-slate-200 outline-none focus:border-slate-500 w-44"
                />
                <div className="text-slate-600 text-xs font-mono mt-0.5">{toKey(newStateName) || 'state-key'}</div>
              </div>
              <div>
                <input
                  value={newStateFirstCity}
                  onChange={e => setNewStateFirstCity(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') addState() }}
                  placeholder="First city name"
                  className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sm text-slate-200 outline-none focus:border-slate-500 w-44"
                />
                <div className="text-slate-600 text-xs font-mono mt-0.5">{toKey(newStateFirstCity) || 'city-key'}</div>
              </div>
              <div className="flex gap-2 items-start mt-0.5">
                <button onClick={addState} className="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 rounded transition-colors">Add State</button>
                <button onClick={() => { setAddStateOpen(false); setNewStateName(''); setNewStateFirstCity('') }} className="text-xs text-slate-500 hover:text-slate-300 py-1">Cancel</button>
              </div>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setAddStateOpen(true)}
            className="w-full py-3 text-xs text-slate-600 hover:text-slate-400 transition-colors text-center"
          >
            + Add state
          </button>
        )}
      </div>
    </div>
  )
}

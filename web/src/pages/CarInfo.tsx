import { useEffect, useMemo, useState } from 'react'

interface SpecOut {
  id: string
  make: string
  model: string
  variant: string
  year_from: number | null
  year_to: number | null
  features: Record<string, Record<string, boolean>>
  source_url: string
  scraped_at: string
}

interface Config {
  id: string
  name: string
  make: string
  model: string
}

const CURRENT_YEAR = new Date().getFullYear()
const CAR_COLORS = ['text-blue-300', 'text-amber-300', 'text-emerald-300', 'text-purple-300']
const CAR_BORDER = ['border-blue-800/60', 'border-amber-800/60', 'border-emerald-800/60', 'border-purple-800/60']

function carKey(make: string, model: string) { return `${make}|${model}` }

function variantInYear(spec: SpecOut, year: number): boolean {
  if (spec.year_from === null) return true
  const to = spec.year_to ?? CURRENT_YEAR
  return year >= spec.year_from && year <= to
}

function sortByYear(specs: SpecOut[]): SpecOut[] {
  return [...specs].sort((a, b) => (a.year_from ?? 0) - (b.year_from ?? 0))
}

function activeFeatures(spec: SpecOut): Set<string> {
  const set = new Set<string>()
  Object.entries(spec.features).forEach(([cat, feats]) => {
    Object.entries(feats).forEach(([feat, val]) => {
      if (val === true) set.add(`${cat}|||${feat}`)
    })
  })
  return set
}

function diffSpecs(prev: SpecOut, curr: SpecOut) {
  const prevFeats = activeFeatures(prev)
  const currFeats = activeFeatures(curr)
  const added: { cat: string; feat: string }[] = []
  const removed: { cat: string; feat: string }[] = []
  currFeats.forEach(key => {
    if (!prevFeats.has(key)) {
      const [cat, feat] = key.split('|||')
      added.push({ cat, feat })
    }
  })
  prevFeats.forEach(key => {
    if (!currFeats.has(key)) {
      const [cat, feat] = key.split('|||')
      removed.push({ cat, feat })
    }
  })
  return { added, removed }
}

// ── Generations view ──────────────────────────────────────────────────────────

function GenerationsView({ specs }: { specs: SpecOut[] }) {
  const sorted = useMemo(() => sortByYear(specs), [specs])
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set([sorted.length - 1]))

  const toggle = (i: number) =>
    setExpanded(prev => {
      const s = new Set(prev)
      if (s.has(i)) s.delete(i); else s.add(i)
      return s
    })

  return (
    <div className="space-y-2">
      {/* Compact timeline strip */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1 flex-wrap">
        {sorted.map((spec, i) => {
          const diff = i > 0 ? diffSpecs(sorted[i - 1], spec) : null
          const hasChanges = diff && (diff.added.length > 0 || diff.removed.length > 0)
          return (
            <div key={spec.id} className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => toggle(i)}
                className={`text-left px-2 py-1 rounded text-xs transition-colors ${
                  expanded.has(i) ? 'bg-slate-700 text-slate-100' : 'bg-slate-800/50 text-slate-400 hover:text-slate-200'
                }`}
              >
                <div className="truncate max-w-[10rem]">{spec.variant}</div>
                <div className="text-[10px] text-slate-600 font-mono">
                  {spec.year_from ?? '?'}–{spec.year_to ?? 'now'}
                </div>
              </button>
              {i < sorted.length - 1 && (
                <span className={`text-[10px] px-0.5 ${hasChanges ? 'text-slate-500' : 'text-slate-700'}`}>→</span>
              )}
            </div>
          )
        })}
      </div>

      {/* Generation cards */}
      <div className="space-y-1.5">
        {sorted.map((spec, i) => {
          const diff = i > 0 ? diffSpecs(sorted[i - 1], spec) : null
          const isFirst = i === 0
          const noChange = diff && diff.added.length === 0 && diff.removed.length === 0
          const isOpen = expanded.has(i)

          return (
            <div key={spec.id} className="border border-slate-800 rounded-lg overflow-hidden">
              <button
                onClick={() => toggle(i)}
                className="w-full flex items-center justify-between px-4 py-2.5 bg-slate-900/60 hover:bg-slate-800/40 transition-colors text-left"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div>
                    <span className="text-sm font-medium text-slate-200">{spec.variant}</span>
                    <span className="ml-2 text-xs text-slate-500 font-mono">
                      {spec.year_from ?? '?'}–{spec.year_to ?? 'now'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs flex-shrink-0 ml-4">
                  {isFirst && (
                    <span className="text-slate-600">{activeFeatures(spec).size} features</span>
                  )}
                  {diff && diff.added.length > 0 && (
                    <span className="bg-emerald-900/40 text-emerald-400 border border-emerald-800/40 px-1.5 py-0.5 rounded font-mono">
                      +{diff.added.length}
                    </span>
                  )}
                  {diff && diff.removed.length > 0 && (
                    <span className="bg-red-900/40 text-red-400 border border-red-800/40 px-1.5 py-0.5 rounded font-mono">
                      −{diff.removed.length}
                    </span>
                  )}
                  {noChange && <span className="text-slate-700 text-[11px]">no change</span>}
                  <span className="text-slate-700 text-[10px]">{isOpen ? '▲' : '▼'}</span>
                </div>
              </button>

              {isOpen && (
                <div className="px-4 py-3 border-t border-slate-800/60 space-y-3">
                  {isFirst && (
                    <div>
                      <div className="text-xs text-slate-600 mb-2">Base generation — {activeFeatures(spec).size} features</div>
                      <div className="flex flex-wrap gap-1.5">
                        {[...activeFeatures(spec)].sort().map(key => {
                          const [, feat] = key.split('|||')
                          return (
                            <span key={key} className="text-[11px] bg-slate-800 text-slate-400 border border-slate-700/50 px-1.5 py-0.5 rounded">
                              {feat}
                            </span>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {diff && diff.added.length > 0 && (
                    <div>
                      <div className="text-xs font-medium text-emerald-500 mb-2">Added ({diff.added.length})</div>
                      <div className="flex flex-wrap gap-1.5">
                        {diff.added.map(({ cat, feat }) => (
                          <span
                            key={`${cat}-${feat}`}
                            className="text-xs bg-emerald-900/25 text-emerald-300 border border-emerald-800/40 px-2 py-0.5 rounded"
                            title={cat}
                          >
                            {feat}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {diff && diff.removed.length > 0 && (
                    <div>
                      <div className="text-xs font-medium text-red-500 mb-2">Removed ({diff.removed.length})</div>
                      <div className="flex flex-wrap gap-1.5">
                        {diff.removed.map(({ cat, feat }) => (
                          <span
                            key={`${cat}-${feat}`}
                            className="text-xs bg-red-900/25 text-red-300 border border-red-800/40 px-2 py-0.5 rounded"
                            title={cat}
                          >
                            {feat}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {noChange && (
                    <div className="text-xs text-slate-600">Same features as previous generation.</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Compare table (diff-only by default) ──────────────────────────────────────

function CompareTable({
  columns,
  diffOnly,
  onToggleDiff,
}: {
  columns: { spec: SpecOut; carIdx: number }[]
  diffOnly: boolean
  onToggleDiff: () => void
}) {
  const allCategories = useMemo(() => {
    const seen = new Set<string>()
    const order: string[] = []
    columns.forEach(({ spec: s }) =>
      Object.keys(s.features).forEach(cat => { if (!seen.has(cat)) { seen.add(cat); order.push(cat) } })
    )
    return order
  }, [columns])

  const allFeatures = useMemo(() => {
    const map: Record<string, string[]> = {}
    allCategories.forEach(cat => {
      const seen = new Set<string>()
      const order: string[] = []
      columns.forEach(({ spec: s }) =>
        Object.keys(s.features[cat] ?? {}).forEach(f => { if (!seen.has(f)) { seen.add(f); order.push(f) } })
      )
      map[cat] = order
    })
    return map
  }, [columns, allCategories])

  const isDiffRow = (cat: string, feat: string) => {
    if (!diffOnly || columns.length < 2) return true
    const vals = columns.map(({ spec: s }) => s.features[cat]?.[feat])
    return !vals.every(v => v === vals[0])
  }

  const visibleCategories = useMemo(
    () => allCategories.filter(cat => allFeatures[cat].some(f => isDiffRow(cat, f))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [allCategories, allFeatures, diffOnly, columns]
  )

  const totalDiff = visibleCategories.reduce(
    (n, cat) => n + allFeatures[cat].filter(f => isDiffRow(cat, f)).length,
    0
  )

  if (columns.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-2">
        <span className="text-xs text-slate-600">
          {diffOnly ? `${totalDiff} differing features` : 'All features'}
        </span>
        <button
          onClick={onToggleDiff}
          className="text-xs text-slate-400 hover:text-slate-200 bg-slate-800 border border-slate-700 px-2.5 py-1 rounded transition-colors"
        >
          {diffOnly ? 'Show all' : 'Diff only'}
        </button>
      </div>

      <div className="overflow-auto max-h-[calc(100vh-22rem)] rounded border border-slate-800">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="sticky top-0 z-20 bg-slate-900">
              <th className="sticky left-0 z-30 bg-slate-900 text-left px-3 py-2.5 font-medium text-slate-400 border-b border-slate-700 min-w-44 w-44">
                Feature
              </th>
              {columns.map(({ spec: s, carIdx }) => (
                <th
                  key={s.id}
                  className="px-3 py-2.5 text-center font-medium border-b border-l border-slate-700 min-w-36 whitespace-nowrap"
                >
                  <div className={CAR_COLORS[carIdx % CAR_COLORS.length]}>{s.variant}</div>
                  <div className="text-slate-500 font-normal text-[10px] mt-0.5">
                    {s.make} {s.model}
                    {s.year_from && (
                      <span className="ml-1 font-mono">{s.year_from}–{s.year_to ?? 'now'}</span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(diffOnly ? visibleCategories : allCategories).map(cat => {
              const rows = allFeatures[cat].filter(f => isDiffRow(cat, f))
              if (diffOnly && rows.length === 0) return null
              const displayRows = diffOnly ? rows : allFeatures[cat]
              return (
                <>
                  <tr key={`cat-${cat}`} className="bg-slate-900/60">
                    <td
                      colSpan={columns.length + 1}
                      className="sticky left-0 px-3 py-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider border-t border-slate-800"
                    >
                      {cat}
                      {diffOnly && rows.length > 0 && (
                        <span className="ml-1.5 font-normal text-slate-600 normal-case tracking-normal">
                          ({rows.length} differ)
                        </span>
                      )}
                    </td>
                  </tr>
                  {displayRows.map(feat => (
                    <tr key={`${cat}-${feat}`} className="hover:bg-slate-800/40 transition-colors">
                      <td className="sticky left-0 z-10 bg-[#0f1117] px-3 py-1.5 text-slate-300 border-t border-slate-800/60">
                        {feat}
                      </td>
                      {columns.map(({ spec: s, carIdx }) => {
                        const val = s.features[cat]?.[feat]
                        return (
                          <td
                            key={s.id}
                            className={`px-3 py-1.5 text-center border-t border-l ${CAR_BORDER[carIdx % CAR_BORDER.length]}/30`}
                          >
                            {val === true ? (
                              <span className={CAR_COLORS[carIdx % CAR_COLORS.length]}>✓</span>
                            ) : val === false ? (
                              <span className="text-slate-700">✗</span>
                            ) : (
                              <span className="text-slate-700">—</span>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildYearOptions(specsList: SpecOut[][]): number[] {
  const years = new Set<number>()
  specsList.flat().forEach(s => {
    if (s.year_from) {
      const end = s.year_to ?? CURRENT_YEAR
      for (let y = s.year_from; y <= end; y++) years.add(y)
    }
  })
  return Array.from(years).sort((a, b) => b - a)
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function CarInfo() {
  const [configs, setConfigs] = useState<Config[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [specsCache, setSpecsCache] = useState<Record<string, SpecOut[]>>({})
  const [loadingCars, setLoadingCars] = useState<Set<string>>(new Set())
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [variantPicks, setVariantPicks] = useState<Record<string, string>>({})
  const [yearFilter, setYearFilter] = useState<number | null>(null)
  const [viewMode, setViewMode] = useState<'generations' | 'compare'>('generations')
  const [diffOnly, setDiffOnly] = useState(true)

  useEffect(() => {
    fetch('/api/configs/').then(r => r.json()).then(setConfigs).catch(() => {})
  }, [])

  const uniqueCars = useMemo(() => {
    const seen = new Set<string>()
    return configs.filter(c => {
      const k = carKey(c.make, c.model)
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
  }, [configs])

  const loadSpecs = async (make: string, model: string) => {
    const k = carKey(make, model)
    setLoadingCars(prev => new Set([...prev, k]))
    setErrors(prev => ({ ...prev, [k]: '' }))
    try {
      const existing: SpecOut[] = await fetch(
        `/api/specs/?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
      ).then(r => r.json())
      if (existing.length > 0) {
        setSpecsCache(prev => ({ ...prev, [k]: existing }))
        return
      }
      const res = await fetch('/api/specs/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ make, model }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setErrors(prev => ({ ...prev, [k]: err.detail ?? 'Fetch failed' }))
        return
      }
      const { scraped } = await res.json()
      if (scraped === 0) {
        setErrors(prev => ({ ...prev, [k]: 'No spec data found.' }))
        return
      }
      const data: SpecOut[] = await fetch(
        `/api/specs/?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
      ).then(r => r.json())
      setSpecsCache(prev => ({ ...prev, [k]: data }))
    } catch {
      setErrors(prev => ({ ...prev, [k]: 'Network error' }))
    } finally {
      setLoadingCars(prev => { const s = new Set(prev); s.delete(k); return s })
    }
  }

  const toggleCar = (make: string, model: string) => {
    const k = carKey(make, model)
    if (selected.includes(k)) {
      setSelected(prev => prev.filter(x => x !== k))
      return
    }
    const next = [...selected, k]
    setSelected(next)
    setViewMode(next.length === 1 ? 'generations' : 'compare')
    if (!specsCache[k]) loadSpecs(make, model)
  }

  const refreshSpecs = (make: string, model: string) => {
    const k = carKey(make, model)
    setSpecsCache(prev => { const n = { ...prev }; delete n[k]; return n })
    loadSpecs(make, model)
  }

  const carIdxMap = useMemo(() => {
    const m: Record<string, number> = {}
    selected.forEach((k, i) => { m[k] = i })
    return m
  }, [selected])

  const singleCarSpecs = useMemo((): SpecOut[] => {
    if (selected.length !== 1) return []
    return specsCache[selected[0]] ?? []
  }, [selected, specsCache])

  const columns = useMemo(() => {
    const cols: { spec: SpecOut; carIdx: number }[] = []
    selected.forEach(k => {
      const carIdx = carIdxMap[k]
      const specs = specsCache[k] ?? []
      const picked = variantPicks[k] ?? ''
      const base = picked ? specs.filter(s => s.variant === picked) : specs
      const filtered = yearFilter ? base.filter(s => variantInYear(s, yearFilter)) : base
      filtered.forEach(spec => cols.push({ spec, carIdx }))
    })
    return cols
  }, [selected, specsCache, variantPicks, yearFilter, carIdxMap])

  const yearOptions = useMemo(
    () => buildYearOptions(selected.map(k => specsCache[k] ?? [])),
    [selected, specsCache]
  )

  const hasData = selected.some(k => (specsCache[k] ?? []).length > 0)

  return (
    <div className="space-y-4">

      {/* Car picker + controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-3">
        {uniqueCars.length === 0 ? (
          <div className="text-slate-600 text-xs">No configs yet — add some in Search Configs.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {uniqueCars.map(c => {
              const k = carKey(c.make, c.model)
              const isSelected = selected.includes(k)
              const idx = carIdxMap[k]
              return (
                <button
                  key={k}
                  onClick={() => toggleCar(c.make, c.model)}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors border ${
                    isSelected
                      ? `bg-slate-700 ${CAR_COLORS[idx % CAR_COLORS.length]} ${CAR_BORDER[idx % CAR_BORDER.length]}`
                      : 'bg-slate-800/50 text-slate-400 border-slate-700 hover:text-slate-200 hover:border-slate-600'
                  }`}
                >
                  {c.make} {c.model}
                  {loadingCars.has(k) && <span className="ml-1.5 text-slate-600 animate-pulse">…</span>}
                </button>
              )
            })}
          </div>
        )}

        {selected.length > 0 && (
          <div className="flex flex-wrap items-center gap-4 pt-1 border-t border-slate-800">
            {selected.map(k => {
              const [make, model] = k.split('|')
              const carIdx = carIdxMap[k]
              const specs = specsCache[k] ?? []
              const err = errors[k]
              return (
                <div key={k} className="flex items-center gap-2">
                  <span className={`text-xs font-medium ${CAR_COLORS[carIdx % CAR_COLORS.length]}`}>
                    {make} {model}
                  </span>
                  {err && <span className="text-xs text-red-400">{err}</span>}
                  {!loadingCars.has(k) && !err && specs.length === 0 && (
                    <span className="text-xs text-slate-500">
                      no specs — <button onClick={() => refreshSpecs(make, model)} className="underline hover:text-slate-300">fetch</button>
                    </span>
                  )}
                  {specs.length > 0 && viewMode === 'compare' && (
                    <select
                      value={variantPicks[k] ?? ''}
                      onChange={e => setVariantPicks(prev => ({ ...prev, [k]: e.target.value }))}
                      className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 outline-none focus:border-slate-500"
                    >
                      <option value="">All variants ({specs.length})</option>
                      {specs.map(s => <option key={s.id} value={s.variant}>{s.variant}</option>)}
                    </select>
                  )}
                  {specs.length > 0 && (
                    <button onClick={() => refreshSpecs(make, model)} className="text-xs text-slate-600 hover:text-slate-400" title="Re-fetch specs">↻</button>
                  )}
                </div>
              )
            })}

            <div className="ml-auto flex items-center gap-3">
              {yearOptions.length > 0 && viewMode === 'compare' && (
                <div className="flex items-center gap-2">
                  <label className="text-xs text-slate-500">Year</label>
                  <select
                    value={yearFilter ?? ''}
                    onChange={e => setYearFilter(e.target.value ? Number(e.target.value) : null)}
                    className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 outline-none focus:border-slate-500"
                  >
                    <option value="">All years</option>
                    {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                  </select>
                </div>
              )}
              {hasData && (
                <div className="flex items-center gap-0.5 bg-slate-800 border border-slate-700 rounded-lg p-0.5">
                  <button
                    onClick={() => setViewMode('generations')}
                    className={`px-2.5 py-1 rounded text-xs transition-colors ${viewMode === 'generations' ? 'bg-slate-600 text-slate-100' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    Generations
                  </button>
                  <button
                    onClick={() => setViewMode('compare')}
                    className={`px-2.5 py-1 rounded text-xs transition-colors ${viewMode === 'compare' ? 'bg-slate-600 text-slate-100' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    Compare
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Empty state */}
      {selected.length === 0 && (
        <div className="text-center text-slate-600 py-16 text-sm border border-dashed border-slate-800 rounded-lg">
          Select a car to see its evolution across generations
        </div>
      )}

      {/* Generations view — single car only */}
      {viewMode === 'generations' && singleCarSpecs.length > 0 && (
        <GenerationsView specs={singleCarSpecs} />
      )}
      {viewMode === 'generations' && selected.length > 1 && (
        <div className="text-center text-slate-600 py-8 text-sm border border-dashed border-slate-800 rounded-lg">
          Generations view shows one car at a time — switch to Compare for multi-car
        </div>
      )}

      {/* Compare view */}
      {viewMode === 'compare' && columns.length > 0 && (
        <CompareTable columns={columns} diffOnly={diffOnly} onToggleDiff={() => setDiffOnly(d => !d)} />
      )}
    </div>
  )
}

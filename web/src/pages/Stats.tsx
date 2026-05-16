import { useEffect, useState } from 'react'

interface Config {
  id: string
  name: string
  make: string
  model: string
}

interface CellData {
  min: number
  max: number
  avg: number
  count: number
}

type PriceData = Record<string, Record<string, CellData>>

interface ClusterMember {
  raw: string
  count: number
  score: number
}

interface Cluster {
  canonical_suggestion: string
  members: ClusterMember[]
  total_count: number
  confidence: number
  is_singleton: boolean
}

function fmt_price(p: number) {
  if (p >= 10_000_000) return `₹${(p / 10_000_000).toFixed(2)}Cr`
  return `₹${(p / 100_000).toFixed(2)}L`
}

function price_color(avg: number, globalMin: number, globalMax: number): string {
  if (globalMax === globalMin) return 'bg-slate-800'
  const ratio = (avg - globalMin) / (globalMax - globalMin)
  if (ratio < 0.25) return 'bg-emerald-950 border-emerald-800'
  if (ratio < 0.5) return 'bg-emerald-900/40 border-emerald-800/40'
  if (ratio < 0.75) return 'bg-amber-950/60 border-amber-800/40'
  return 'bg-red-950/60 border-red-800/40'
}

function score_color(score: number) {
  if (score >= 85) return 'text-emerald-400'
  if (score >= 70) return 'text-amber-400'
  return 'text-red-400'
}

// ── Variant Manager ───────────────────────────────────────────────────────────

function VariantManager({ make, model }: { make: string; model: string }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [clusters, setClusters] = useState<Cluster[]>([])
  // Keyed by canonical_suggestion string (stable across re-analyses) not array index.
  const [canonicals, setCanonicals] = useState<Record<string, string>>({})
  const [applying, setApplying] = useState(false)
  const [result, setResult] = useState<{ updated: number; mappings_applied: number } | null>(null)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(75)

  const suggest = (preserveEdits = false) => {
    setLoading(true)
    if (!preserveEdits) setResult(null)
    fetch(`/api/variants/suggest?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}&threshold=${threshold}`)
      .then(r => r.json())
      .then((data: Cluster[]) => {
        setClusters(data)
        setCanonicals(prev => {
          const next: Record<string, string> = {}
          data.forEach(c => {
            // Keep any edit the user already made, fall back to suggestion.
            next[c.canonical_suggestion] = prev[c.canonical_suggestion] ?? c.canonical_suggestion
          })
          return next
        })
        setOpen(true)
      })
      .finally(() => setLoading(false))
  }

  const apply = async () => {
    setApplying(true)
    setResult(null)
    setApplyError(null)
    try {
      const mappings: { raw: string; canonical: string }[] = []
      clusters.forEach(cluster => {
        const canonical = canonicals[cluster.canonical_suggestion]?.trim()
        if (!canonical) return  // empty = user skipped this group with ×
        cluster.members.forEach(m => {
          mappings.push({ raw: m.raw, canonical })
        })
      })
      const res = await fetch('/api/variants/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ make, model, mappings }),
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setResult(data)
      suggest(true)
    } catch (e) {
      setApplyError(e instanceof Error ? e.message : 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  const isLowConf = (c: Cluster) => c.confidence < 80 && !c.is_singleton
  const nonSingletons = clusters.filter(c => !c.is_singleton)
  const singletons = clusters.filter(c => c.is_singleton)

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800/50 transition-colors"
        onClick={() => !loading && (open ? setOpen(false) : suggest())}
      >
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-300 font-medium">Fix Variant Names</span>
          <span className="text-xs text-slate-500">
            {make} {model} — group similar names into one
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-slate-500" onClick={e => e.stopPropagation()}>
              Match sensitivity
            </label>
            <input
              type="number"
              value={threshold}
              min={50}
              max={99}
              onClick={e => e.stopPropagation()}
              onChange={e => setThreshold(+e.target.value)}
              className="w-14 bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-xs text-slate-200 outline-none focus:border-slate-500"
            />
            <span className="text-xs text-slate-600">%</span>
          </div>
          <span className="text-slate-500 text-xs">
            {loading ? 'Analyzing…' : open ? '▲' : '▶ Analyze'}
          </span>
        </div>
      </button>

      {open && clusters.length > 0 && (
        <div className="border-t border-slate-800">
          {result && (
            <div className="px-4 py-2 bg-emerald-950/60 border-b border-emerald-800/40 flex items-center justify-between">
              <span className="text-xs text-emerald-300 font-mono">
                ✓ {result.updated} listing{result.updated !== 1 ? 's' : ''} updated
                · {result.mappings_applied} mapping{result.mappings_applied !== 1 ? 's' : ''} applied
              </span>
              <button onClick={() => setResult(null)} className="text-xs text-emerald-600 hover:text-emerald-400">dismiss</button>
            </div>
          )}
          {applyError && (
            <div className="px-4 py-2 bg-red-950/60 border-b border-red-800/40 flex items-center justify-between">
              <span className="text-xs text-red-300 font-mono">{applyError}</span>
              <button onClick={() => setApplyError(null)} className="text-xs text-red-600 hover:text-red-400">dismiss</button>
            </div>
          )}

          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              {nonSingletons.length} groups · {singletons.length} already unique
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => suggest()}
                disabled={loading}
                className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded hover:bg-slate-800 disabled:opacity-40"
              >
                re-analyze
              </button>
              <button
                onClick={apply}
                disabled={applying || loading}
                className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-slate-100 text-xs px-3 py-1.5 rounded"
              >
                {applying ? 'Applying…' : 'Apply all'}
              </button>
            </div>
          </div>

          <div className="divide-y divide-slate-800/50 max-h-[32rem] overflow-y-auto">
            {nonSingletons.map((cluster) => {
              const key = cluster.canonical_suggestion
              const isLow = isLowConf(cluster)
              const isSkipped = (canonicals[key] ?? '').trim() === ''
              return (
                <div
                  key={key}
                  className={`px-4 py-3 transition-opacity ${isSkipped ? 'opacity-40' : ''} ${isLow && !isSkipped ? 'border-l-2 border-amber-700/60' : ''}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs text-slate-500 w-16 shrink-0">Standard name</span>
                    <input
                      value={canonicals[key] ?? ''}
                      onChange={e => setCanonicals(prev => ({ ...prev, [key]: e.target.value }))}
                      disabled={isSkipped}
                      className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100 outline-none focus:border-slate-500 font-medium disabled:cursor-not-allowed"
                      placeholder="Canonical variant name…"
                    />
                    {!isSkipped && isLow && (
                      <span className="text-xs text-amber-500/80 shrink-0">review recommended</span>
                    )}
                    {isSkipped && (
                      <span className="text-xs text-slate-600 shrink-0">excluded</span>
                    )}
                    <button
                      onClick={() => setCanonicals(prev => ({
                        ...prev,
                        [key]: isSkipped ? cluster.canonical_suggestion : '',
                      }))}
                      className="text-slate-500 hover:text-slate-200 text-sm leading-none shrink-0 w-4"
                      title={isSkipped ? 'Include this group' : 'Skip this group'}
                    >
                      {isSkipped ? '+' : '×'}
                    </button>
                  </div>
                  {!isSkipped && (
                    <div className="space-y-0.5 ml-[4.5rem]">
                      {cluster.members.map((m, mi) => (
                        <div key={mi} className="flex items-center gap-2 text-xs">
                          <span className="text-slate-400 flex-1 font-mono">{m.raw}</span>
                          <span className="text-slate-600 tabular-nums">{m.count} listing{m.count !== 1 ? 's' : ''}</span>
                          <span className={`tabular-nums font-mono ${score_color(m.score)}`}>
                            {m.score === 100 ? '—' : `${m.score}%`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}

            {singletons.length > 0 && (
              <div className="px-4 py-3">
                <div className="text-xs text-slate-600 mb-2">Unique variants (no merge needed)</div>
                <div className="flex flex-wrap gap-1.5">
                  {singletons.map((c, si) => (
                    <span
                      key={si}
                      className="bg-slate-800 text-slate-400 text-xs px-2 py-0.5 rounded font-mono"
                      title={`${c.members[0]?.count ?? 0} listing(s)`}
                    >
                      {c.canonical_suggestion}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {open && clusters.length === 0 && !loading && (
        <div className="border-t border-slate-800 px-4 py-6 text-center text-xs text-slate-500">
          {result
            ? `All variants normalised — ${result.updated} listing${result.updated !== 1 ? 's' : ''} updated.`
            : `No unconfirmed variants for ${make} ${model}.`}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Stats() {
  const [configs, setConfigs] = useState<Config[]>([])
  const [make, setMake] = useState('')
  const [model, setModel] = useState('')
  const [data, setData] = useState<PriceData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/configs/')
      .then(r => r.json())
      .then(setConfigs)
  }, [])

  const load = () => {
    if (!make.trim() || !model.trim()) return
    setLoading(true)
    setError('')
    setData(null)
    fetch(`/api/stats/price-range?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`)
      .then(r => r.json())
      .then(d => {
        if (Object.keys(d).length === 0) setError('No data for this make + model. Run a scrape first.')
        else setData(d)
      })
      .catch(() => setError('Failed to load stats.'))
      .finally(() => setLoading(false))
  }

  const pickConfig = (cfg: Config) => {
    setMake(cfg.make)
    setModel(cfg.model)
    setData(null)
    setError('')
  }

  const variants = data ? Object.keys(data).sort() : []
  const yearsSet = new Set<string>()
  if (data) variants.forEach(v => Object.keys(data[v]).forEach(y => yearsSet.add(y)))
  const years = Array.from(yearsSet).sort()

  let globalMin = Infinity
  let globalMax = -Infinity
  if (data) {
    variants.forEach(v =>
      years.forEach(y => {
        const cell = data[v]?.[y]
        if (cell) {
          if (cell.avg < globalMin) globalMin = cell.avg
          if (cell.avg > globalMax) globalMax = cell.avg
        }
      })
    )
  }

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-4">
        <div className="flex items-end gap-3">
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Make</label>
            <input
              value={make}
              onChange={e => setMake(e.target.value)}
              placeholder="Volkswagen"
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-slate-500 placeholder:text-slate-600 w-36"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Model</label>
            <input
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder="Vento"
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-slate-500 placeholder:text-slate-600 w-36"
              onKeyDown={e => e.key === 'Enter' && load()}
            />
          </div>
          <button
            onClick={load}
            disabled={!make || !model}
            className="bg-slate-600 hover:bg-slate-500 disabled:opacity-30 text-slate-100 text-xs px-4 py-1.5 rounded"
          >
            {loading ? 'Loading…' : 'Load stats'}
          </button>
        </div>

        {configs.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-slate-600">Quick pick:</span>
            {configs.map(c => (
              <button
                key={c.id}
                onClick={() => pickConfig(c)}
                className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                  make === c.make && model === c.model
                    ? 'border-slate-500 bg-slate-700 text-slate-200'
                    : 'border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-600'
                }`}
              >
                {c.make} {c.model}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="text-slate-500 text-sm text-center py-8 border border-dashed border-slate-800 rounded-lg">
          {error}
        </div>
      )}

      {data && variants.length > 0 && (
        <>
          <div className="text-xs text-slate-500">
            {make} {model} — {variants.length} variant{variants.length !== 1 ? 's' : ''}, {years.length} year{years.length !== 1 ? 's' : ''}
          </div>

          {/* Legend */}
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span>Price:</span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-emerald-950 border border-emerald-800 inline-block" /> low
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-amber-950/60 border border-amber-800/40 inline-block" /> mid
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-red-950/60 border border-red-800/40 inline-block" /> high
            </span>
          </div>

          {/* Matrix */}
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="text-left px-3 py-2 font-normal min-w-[180px]">Variant</th>
                  {years.map(y => (
                    <th key={y} className="text-center px-3 py-2 font-normal min-w-[120px]">{y}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {variants.map((v, vi) => (
                  <tr
                    key={v}
                    className={`border-b border-slate-800/50 ${vi % 2 === 0 ? 'bg-transparent' : 'bg-slate-900/20'}`}
                  >
                    <td className="px-3 py-2 text-slate-300 font-medium max-w-[200px] truncate" title={v}>{v}</td>
                    {years.map(y => {
                      const cell = data[v]?.[y]
                      if (!cell) return <td key={y} className="px-3 py-2 text-center text-slate-700">—</td>
                      return (
                        <td key={y} className="px-2 py-1.5">
                          <div className={`rounded border p-1.5 text-center ${price_color(cell.avg, globalMin, globalMax)}`}>
                            <div className="text-slate-200 font-mono font-medium">{fmt_price(cell.avg)}</div>
                            <div className="text-slate-500 mt-0.5">{fmt_price(cell.min)} – {fmt_price(cell.max)}</div>
                            <div className="text-slate-600 mt-0.5">{cell.count} listing{cell.count !== 1 ? 's' : ''}</div>
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Variant Manager — shown as soon as a make+model is entered */}
      {make && model && (
        <VariantManager make={make} model={model} />
      )}
    </div>
  )
}

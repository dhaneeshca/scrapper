import { useEffect, useRef, useState } from 'react'

interface Config {
  id: string
  name: string
  make: string
  model: string
  variants: string[]
  year_min: number | null
  year_max: number | null
  fuel_types: string[]
  transmissions: string[]
  budget_max: number | null
  regions: string[]
  is_active: boolean
  created_at: string
}

const BLANK: Omit<Config, 'id' | 'is_active' | 'created_at'> = {
  name: '',
  make: '',
  model: '',
  variants: [],
  year_min: null,
  year_max: null,
  fuel_types: [],
  transmissions: [],
  budget_max: null,
  regions: [],
}

function TagInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string[]
  onChange: (v: string[]) => void
}) {
  const [input, setInput] = useState('')

  const add = () => {
    const v = input.trim()
    if (v && !value.includes(v)) onChange([...value, v])
    setInput('')
  }

  return (
    <div>
      <label className="text-xs text-slate-400 mb-1 block">{label}</label>
      <div className="flex flex-wrap gap-1 mb-1">
        {value.map(tag => (
          <span
            key={tag}
            className="bg-slate-700 text-slate-200 text-xs px-2 py-0.5 rounded flex items-center gap-1"
          >
            {tag}
            <button
              onClick={() => onChange(value.filter(t => t !== tag))}
              className="text-slate-400 hover:text-red-400"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), add())}
          placeholder="type and press Enter"
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 flex-1 outline-none focus:border-slate-500"
        />
        <button
          onClick={add}
          className="bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs px-2 py-1 rounded"
        >
          +
        </button>
      </div>
    </div>
  )
}

function ConfigForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: Omit<Config, 'id' | 'is_active' | 'created_at'>
  onSave: (data: typeof initial) => void
  onCancel: () => void
}) {
  const [form, setForm] = useState(initial)
  const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-5 space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {(['name', 'make', 'model'] as const).map(k => (
          <div key={k} className={k === 'name' ? 'col-span-2' : ''}>
            <label className="text-xs text-slate-400 mb-1 block capitalize">{k}</label>
            <input
              value={form[k]}
              onChange={e => set(k, e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-slate-500"
            />
          </div>
        ))}

        <div>
          <label className="text-xs text-slate-400 mb-1 block">Year min</label>
          <input
            type="number"
            value={form.year_min ?? ''}
            onChange={e => set('year_min', e.target.value ? +e.target.value : null)}
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-slate-500"
          />
        </div>
        <div>
          <label className="text-xs text-slate-400 mb-1 block">Year max</label>
          <input
            type="number"
            value={form.year_max ?? ''}
            onChange={e => set('year_max', e.target.value ? +e.target.value : null)}
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-slate-500"
          />
        </div>
        <div className="col-span-2">
          <label className="text-xs text-slate-400 mb-1 block">Budget max (₹)</label>
          <input
            type="number"
            value={form.budget_max ?? ''}
            onChange={e => set('budget_max', e.target.value ? +e.target.value : null)}
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-slate-500"
          />
        </div>
      </div>

      <TagInput label="Variants" value={form.variants} onChange={v => set('variants', v)} />
      <TagInput label="Fuel types" value={form.fuel_types} onChange={v => set('fuel_types', v)} />
      <TagInput label="Transmissions" value={form.transmissions} onChange={v => set('transmissions', v)} />
      <TagInput label="Regions / Cities" value={form.regions} onChange={v => set('regions', v)} />

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onSave(form)}
          className="bg-slate-600 hover:bg-slate-500 text-slate-100 text-sm px-4 py-1.5 rounded"
        >
          Save
        </button>
        <button
          onClick={onCancel}
          className="text-slate-400 hover:text-slate-200 text-sm px-3 py-1.5"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

interface SourceStats {
  [source: string]: number
}

interface ProgressEvent {
  type: 'run_start' | 'scraper_start' | 'scraper_done' | 'scraper_error' | 'done'
  run_id?: string
  source?: string
  regions?: string[]
  inserted?: number
  updated?: number
  price_changes?: number
  errors?: string[]
  message?: string
}

const SOURCE_COLORS: Record<string, string> = {
  cardekho: 'text-orange-400',
  carwale: 'text-blue-400',
  cars24: 'text-green-400',
  olx: 'text-purple-400',
  spinny: 'text-cyan-400',
  cartrade: 'text-rose-400',
}

// ── Live scrape log ────────────────────────────────────────────────────────────

function ScrapeLog({ events }: { events: ProgressEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [events])

  if (events.length === 0) return null

  const runId = events.find(e => e.type === 'run_start')?.run_id

  return (
    <div className="mt-3 bg-slate-950 border border-slate-800 rounded p-2.5 font-mono text-xs space-y-0.5 max-h-44 overflow-y-auto">
      {runId && (
        <div className="text-slate-600 pb-1 mb-1 border-b border-slate-800">
          run <span className="text-slate-500">{runId}</span>
          <span className="ml-2 text-slate-700">· grep [{runId}] log.txt</span>
        </div>
      )}
      {events.map((ev, i) => {
        const srcColor = ev.source ? (SOURCE_COLORS[ev.source] ?? 'text-slate-400') : 'text-slate-400'
        if (ev.type === 'run_start') return null
        if (ev.type === 'scraper_start') {
          const regions = ev.regions?.length ? ev.regions.join(', ') : 'all regions'
          return (
            <div key={i} className="flex items-center gap-2 text-slate-500">
              <span className={`w-20 shrink-0 ${srcColor}`}>{ev.source}</span>
              <span className="animate-pulse">●</span>
              <span>scraping {regions}…</span>
            </div>
          )
        }
        if (ev.type === 'scraper_done') {
          const parts = []
          if (ev.inserted) parts.push(<span key="i" className="text-emerald-400">↑{ev.inserted}</span>)
          if (ev.updated) parts.push(<span key="u" className="text-slate-400">↻{ev.updated}</span>)
          if (ev.price_changes) parts.push(<span key="p" className="text-amber-400">±{ev.price_changes}</span>)
          if (!parts.length) parts.push(<span key="n" className="text-slate-600">no changes</span>)
          return (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-20 shrink-0 ${srcColor}`}>{ev.source}</span>
              <span className="text-slate-600">✓</span>
              <span className="flex gap-2">{parts}</span>
            </div>
          )
        }
        if (ev.type === 'scraper_error') {
          return (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-20 shrink-0 ${srcColor}`}>{ev.source}</span>
              <span className="text-red-500">✗ {ev.message}</span>
            </div>
          )
        }
        if (ev.type === 'done') {
          const total_new = ev.inserted ?? 0
          const total_upd = ev.updated ?? 0
          const errs = ev.errors ?? []
          return (
            <div key={i} className="flex items-center gap-2 pt-1 mt-1 border-t border-slate-800 text-slate-300">
              <span className="w-20 shrink-0 text-slate-500">total</span>
              {total_new > 0 && <span className="text-emerald-400">↑{total_new} new</span>}
              {total_upd > 0 && <span>↻{total_upd} updated</span>}
              {(ev.price_changes ?? 0) > 0 && <span className="text-amber-400">±{ev.price_changes} price changes</span>}
              {errs.length > 0 && <span className="text-red-400">{errs.length} error{errs.length > 1 ? 's' : ''}</span>}
              {total_new === 0 && total_upd === 0 && errs.length === 0 && <span className="text-slate-600">nothing changed</span>}
            </div>
          )
        }
        return null
      })}
      <div ref={bottomRef} />
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function SearchConfigs() {
  const [configs, setConfigs] = useState<Config[]>([])
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [scraping, setScraping] = useState<Set<string>>(new Set())
  const [sourceStats, setSourceStats] = useState<Record<string, SourceStats>>({})
  // key → accumulated progress events for that scrape run
  const [scrapeLog, setScrapeLog] = useState<Record<string, ProgressEvent[]>>({})

  const loadStats = (ids: string[]) => {
    ids.forEach(id => {
      fetch(`/api/stats/config/${id}/sources`)
        .then(r => r.json())
        .then(data => setSourceStats(prev => ({ ...prev, [id]: data })))
    })
  }

  const load = () =>
    fetch('/api/configs/')
      .then(r => r.json())
      .then((cfgs: Config[]) => {
        setConfigs(cfgs)
        loadStats(cfgs.map(c => c.id))
      })

  useEffect(() => { load() }, [])

  const create = async (data: typeof BLANK) => {
    await fetch('/api/configs/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
    setCreating(false)
    load()
  }

  const update = async (id: string, data: typeof BLANK) => {
    await fetch(`/api/configs/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
    setEditing(null)
    load()
  }

  const remove = async (id: string) => {
    if (!confirm('Delete this config?')) return
    await fetch(`/api/configs/${id}`, { method: 'DELETE' })
    load()
  }

  const toggle = async (id: string) => {
    await fetch(`/api/configs/${id}/toggle`, { method: 'POST' })
    load()
  }

  const startStream = (key: string, url: string, configId: string) => {
    setScraping(prev => new Set([...prev, key]))
    setScrapeLog(prev => ({ ...prev, [key]: [] }))

    const es = new EventSource(url)
    es.onmessage = (e) => {
      const event: ProgressEvent = JSON.parse(e.data)
      setScrapeLog(prev => ({ ...prev, [key]: [...(prev[key] ?? []), event] }))
      if (event.type === 'done') {
        es.close()
        setScraping(prev => { const s = new Set(prev); s.delete(key); return s })
        loadStats([configId])
      }
    }
    es.onerror = () => {
      es.close()
      setScraping(prev => { const s = new Set(prev); s.delete(key); return s })
    }
  }

  const scrapeOne = (id: string) =>
    startStream(id, `/api/scrape/${id}/stream`, id)

  const scrapeSource = (configId: string, source: string) =>
    startStream(`${configId}:${source}`, `/api/scrape/${configId}/stream?source=${source}`, configId)

  const isScrapingAny = (id: string) => scraping.has(id) || ['cardekho','cars24','carwale','olx','spinny','cartrade'].some(s => scraping.has(`${id}:${s}`))
  const isScrapingSource = (id: string, src: string) => scraping.has(`${id}:${src}`) || scraping.has(id)

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-slate-200 font-medium">Search Configs</h2>
        <button
          onClick={() => setCreating(true)}
          className="bg-slate-700 hover:bg-slate-600 text-slate-100 text-sm px-3 py-1.5 rounded"
        >
          + New config
        </button>
      </div>

      {creating && (
        <ConfigForm
          initial={BLANK}
          onSave={create}
          onCancel={() => setCreating(false)}
        />
      )}

      {configs.map(c => (
        <div key={c.id} className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          {editing === c.id ? (
            <ConfigForm
              initial={c}
              onSave={d => update(c.id, d)}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-100 font-medium">{c.name}</span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        c.is_active ? 'bg-emerald-900 text-emerald-300' : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {c.is_active ? 'active' : 'paused'}
                    </span>
                  </div>
                  <div className="text-slate-400 text-sm mt-0.5">
                    {c.make} {c.model}
                    {c.year_min || c.year_max
                      ? ` · ${c.year_min ?? ''}–${c.year_max ?? ''}`
                      : ''}
                    {c.budget_max ? ` · ≤ ₹${(c.budget_max / 100000).toFixed(1)}L` : ''}
                  </div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {c.variants.map(v => (
                      <span key={v} className="bg-slate-800 text-slate-300 text-xs px-1.5 py-0.5 rounded">{v}</span>
                    ))}
                    {c.regions.map(r => (
                      <span key={r} className="bg-slate-800 text-blue-300 text-xs px-1.5 py-0.5 rounded">{r}</span>
                    ))}
                    {c.fuel_types.map(f => (
                      <span key={f} className="bg-slate-800 text-amber-300 text-xs px-1.5 py-0.5 rounded">{f}</span>
                    ))}
                  </div>

                  {/* Per-source rows */}
                  <div className="mt-3 pt-3 border-t border-slate-800 space-y-1.5">
                    {(['cardekho', 'cars24', 'carwale', 'olx', 'spinny', 'cartrade'] as const).map(src => {
                      const count = sourceStats[c.id]?.[src] ?? null
                      const busy = isScrapingSource(c.id, src)
                      return (
                        <div key={src} className="flex items-center gap-2">
                          <span className={`text-xs font-mono w-20 ${count ? SOURCE_COLORS[src] : 'text-slate-600'}`}>
                            {src}
                          </span>
                          <span className={`text-xs font-mono w-6 text-right ${count ? 'text-slate-300' : 'text-slate-700'}`}>
                            {count ?? '—'}
                          </span>
                          <button
                            onClick={() => scrapeSource(c.id, src)}
                            disabled={busy || isScrapingAny(c.id)}
                            className="text-xs text-slate-600 hover:text-slate-300 px-1.5 py-0.5 rounded hover:bg-slate-800 disabled:opacity-30 transition-colors"
                          >
                            {busy ? '…' : '▶'}
                          </button>
                          {scrapeLog[`${c.id}:${src}`]?.slice(-1)[0]?.type === 'scraper_done' && (() => {
                            const last = scrapeLog[`${c.id}:${src}`].slice(-1)[0]
                            return (
                              <span className="text-xs font-mono text-slate-500 flex gap-2">
                                {(last.inserted ?? 0) > 0 && <span className="text-emerald-400">↑{last.inserted}</span>}
                                {(last.updated ?? 0) > 0 && <span>↻{last.updated}</span>}
                                {(last.price_changes ?? 0) > 0 && <span className="text-amber-400">±{last.price_changes}</span>}
                                {!last.inserted && !last.updated && <span>no changes</span>}
                              </span>
                            )
                          })()}
                        </div>
                      )
                    })}
                  </div>

                  {/* Live scrape log — shown for all-sources run or per-source run */}
                  {scrapeLog[c.id] && <ScrapeLog events={scrapeLog[c.id]} />}
                  {['cardekho','cars24','carwale','olx','spinny','cartrade'].map(src =>
                    scrapeLog[`${c.id}:${src}`] && scrapeLog[`${c.id}:${src}`].length > 0 ? (
                      <ScrapeLog key={src} events={scrapeLog[`${c.id}:${src}`]} />
                    ) : null
                  )}
                </div>
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => scrapeOne(c.id)}
                    disabled={isScrapingAny(c.id)}
                    className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded hover:bg-slate-800 disabled:opacity-40"
                    title="Scrape all sources"
                  >
                    {scraping.has(c.id) ? (
                      <span className="flex items-center gap-1">
                        <span className="inline-block w-2 h-2 rounded-full bg-slate-400 animate-pulse" />
                        all…
                      </span>
                    ) : 'scrape all'}
                  </button>
                  <button
                    onClick={() => toggle(c.id)}
                    className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded hover:bg-slate-800"
                  >
                    {c.is_active ? 'pause' : 'resume'}
                  </button>
                  <button
                    onClick={() => setEditing(c.id)}
                    className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded hover:bg-slate-800"
                  >
                    edit
                  </button>
                  <button
                    onClick={() => remove(c.id)}
                    className="text-xs text-red-500 hover:text-red-400 px-2 py-1 rounded hover:bg-slate-800"
                  >
                    del
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      ))}

      {configs.length === 0 && !creating && (
        <div className="text-slate-500 text-sm text-center py-12 border border-dashed border-slate-800 rounded-lg">
          No search configs yet. Create one to start scraping.
        </div>
      )}
    </div>
  )
}

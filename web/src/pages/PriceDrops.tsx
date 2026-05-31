import { useEffect, useState, useCallback } from 'react'
import { SOURCE_COLORS } from '../lib/constants'

interface PricePoint { price: number; observed_at: string }

interface Listing {
  id: string
  source: string
  url: string
  make: string | null
  model: string | null
  variant: string | null
  variant_canonical: string | null
  year: number | null
  km_driven: number | null
  price: number | null
  location_city: string | null
  price_first: number | null
  price_total_delta: number | null
  price_total_pct: number | null
  days_on_market: number | null
  num_price_points: number | null
  price_points: PricePoint[] | null
}

interface CarConfig { id: string; name: string; make: string; model: string }

function fmt_price(p: number | null) {
  if (!p) return '—'
  if (p >= 10_000_000) return `₹${(p / 10_000_000).toFixed(2)} Cr`
  return `₹${(p / 100_000).toFixed(2)} L`
}

function fmt_km(km: number | null) {
  if (!km) return '—'
  return `${km.toLocaleString('en-IN')} km`
}

const fmtDate = (iso: string) => {
  const d = new Date(iso)
  return `${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`
}

function MiniSparkline({ data }: { data: PricePoint[] }) {
  const W = 80, H = 24, PAD = 3
  const prices = data.map(d => d.price)
  const minP = Math.min(...prices), maxP = Math.max(...prices)
  const priceRange = maxP - minP || 1
  const dates = data.map(d => new Date(d.observed_at).getTime())
  const minT = dates[0], timeRange = (dates[dates.length - 1] - minT) || 1
  const toX = (t: number) => PAD + ((t - minT) / timeRange) * (W - PAD * 2)
  const toY = (p: number) => PAD + (1 - (p - minP) / priceRange) * (H - PAD * 2)
  const points = data.map((d, i) => `${toX(dates[i])},${toY(d.price)}`).join(' ')
  const delta = data[data.length - 1].price - data[0].price
  const color = delta < 0 ? '#34d399' : delta > 0 ? '#f87171' : '#64748b'
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="flex-shrink-0">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.25" strokeLinejoin="round" />
      {data.map((d, i) => (
        <circle key={i} cx={toX(dates[i])} cy={toY(d.price)} r={i === data.length - 1 ? 2 : 1.4} fill={color}>
          <title>{`${fmt_price(d.price)} · ${fmtDate(d.observed_at)}`}</title>
        </circle>
      ))}
    </svg>
  )
}

export default function PriceDrops() {
  const [configs, setConfigs] = useState<CarConfig[]>([])
  const [configId, setConfigId] = useState('')
  const [rows, setRows] = useState<Listing[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/configs/')
      .then(r => r.json())
      .then(setConfigs)
      .catch(() => {})
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const p = new URLSearchParams({ price_change: 'drop', sort_by: 'price_drop', limit: '200' })
    if (configId) p.set('config_id', configId)
    fetch(`/api/listings/?${p}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setRows)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [configId])

  useEffect(() => { load() }, [load])

  const carName = (l: Listing) =>
    [l.year, l.make, l.model, l.variant_canonical ?? l.variant].filter(Boolean).join(' ')

  return (
    <div className="max-w-4xl space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-slate-200 font-medium">Price Drops</h2>
          <p className="text-xs text-slate-500 mt-0.5">Cars ranked by biggest drop since first listed — motivated sellers first.</p>
        </div>
        <select
          value={configId}
          onChange={e => setConfigId(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none"
        >
          <option value="">All searches</option>
          {configs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {loading && <div className="text-slate-500 text-sm py-8 text-center">Loading…</div>}
      {error && !loading && (
        <div className="border border-dashed border-red-900/60 rounded p-4 text-center text-sm text-red-400">
          Failed to load price drops: {error}
          <button onClick={load} className="block mx-auto mt-2 text-xs text-slate-400 hover:text-slate-200">retry</button>
        </div>
      )}
      {!loading && !error && rows.length === 0 && (
        <div className="border border-dashed border-slate-800 rounded p-8 text-center text-sm text-slate-600">
          No price drops yet. Drops appear once a listing's price falls across scrape runs.
        </div>
      )}

      {!loading && !error && rows.map(l => {
        const drop = l.price_total_delta ?? 0
        const pct = l.price_total_pct
        return (
          <a
            key={l.id}
            href={l.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-4 bg-slate-900/60 border border-slate-800 rounded px-4 py-2.5 hover:border-slate-700 transition-colors"
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm text-slate-200 truncate">{carName(l)}</div>
              <div className="text-xs text-slate-500 flex items-center gap-1.5 flex-wrap mt-0.5">
                <span>{fmt_km(l.km_driven)}</span>
                {l.location_city && <><span className="text-slate-700">·</span><span>{l.location_city}</span></>}
                <span className="text-slate-700">·</span>
                <span className={`${SOURCE_COLORS[l.source] ?? 'text-slate-400'}`}>{l.source}</span>
                {l.days_on_market != null && <><span className="text-slate-700">·</span><span>{l.days_on_market}d on market</span></>}
              </div>
            </div>

            {l.price_points && l.price_points.length > 1 && <MiniSparkline data={l.price_points} />}

            <div className="flex-shrink-0 text-right">
              <div className="text-base font-mono font-bold text-white">{fmt_price(l.price)}</div>
              <div className="text-[11px] font-mono text-emerald-400">
                ↓{fmt_price(Math.abs(drop))}{pct != null ? ` (${pct}%)` : ''}
              </div>
              {l.price_first != null && (
                <div className="text-[10px] font-mono text-slate-600">was {fmt_price(l.price_first)}</div>
              )}
            </div>
          </a>
        )
      })}
    </div>
  )
}

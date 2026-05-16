import { useEffect, useRef, useState, useCallback } from 'react'

// ── Types ──────────────────────────────────────────────────────────────────────

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
  fuel_type: string | null
  transmission: string | null
  price: number | null
  location_city: string | null
  location_state: string | null
  seller_type: string | null
  images: string[] | null
  description: string | null
  scraped_at: string | null
  is_active: boolean
  is_manually_edited: boolean
  shortlisted: boolean
}

interface DedupGroup {
  dedup_key: string
  best_price: number
  sources: string[]
  listing_ids: string[]
  representative: Listing
}

interface CarConfig {
  id: string
  name: string
  make: string
  model: string
}

interface Filters {
  config_id: string
  source: string
  city: string
  variant: string
  year_min: string
  year_max: string
  price_min: string
  price_max: string
  km_max: string
  fuel_type: string
  transmission: string
  sort_by: string
  sort_dir: string
}

interface Options {
  variants: string[]
  cities: string[]
  fuel_types: string[]
  transmissions: string[]
}

interface FairValueData {
  fair_value: number | null
  p25: number | null
  p75: number | null
  sample_size: number
  active_count: number
  inactive_count: number
}

type PriceRangeMap = Record<string, Record<string, { min: number; max: number; avg: number; count: number }>>

// ── Constants ─────────────────────────────────────────────────────────────────

const INIT_FILTERS: Filters = {
  config_id: '',
  source: '',
  city: '',
  variant: '',
  year_min: '',
  year_max: '',
  price_min: '',
  price_max: '',
  km_max: '',
  fuel_type: '',
  transmission: '',
  sort_by: 'scraped_at',
  sort_dir: 'desc',
}

const SOURCE_COLORS: Record<string, string> = {
  cardekho: 'bg-orange-900/70 text-orange-300 border border-orange-800/50',
  carwale:  'bg-blue-900/70 text-blue-300 border border-blue-800/50',
  cars24:   'bg-green-900/70 text-green-300 border border-green-800/50',
  olx:      'bg-purple-900/70 text-purple-300 border border-purple-800/50',
  spinny:   'bg-cyan-900/70 text-cyan-300 border border-cyan-800/50',
  cartrade: 'bg-rose-900/70 text-rose-300 border border-rose-800/50',
}

const CURRENT_YEAR = new Date().getFullYear()

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt_price(p: number | null) {
  if (!p) return '—'
  if (p >= 10_000_000) return `₹${(p / 10_000_000).toFixed(2)} Cr`
  return `₹${(p / 100_000).toFixed(2)} L`
}

function fmt_km(km: number | null) {
  if (!km) return '—'
  return `${km.toLocaleString('en-IN')} km`
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

interface KmHealthResult { dot: string; title: string }

function kmHealth(km: number | null, year: number | null): KmHealthResult | null {
  if (!km || !year || year >= CURRENT_YEAR) return null
  const age = CURRENT_YEAR - year
  const kpy = km / age
  if (kpy < 2000)  return { dot: 'bg-amber-400',  title: `${Math.round(kpy).toLocaleString('en-IN')} km/yr — suspiciously low` }
  if (kpy <= 18000) return { dot: 'bg-emerald-400', title: `${Math.round(kpy).toLocaleString('en-IN')} km/yr — normal` }
  if (kpy <= 25000) return { dot: 'bg-amber-400',  title: `${Math.round(kpy).toLocaleString('en-IN')} km/yr — above average` }
  return              { dot: 'bg-red-500',    title: `${Math.round(kpy).toLocaleString('en-IN')} km/yr — hard use` }
}

interface DealResult { pct: number; label: string; pillCls: string; borderCls: string }

function dealScore(
  price: number | null,
  variant: string | null,
  year: number | null,
  rangeMap: PriceRangeMap,
): DealResult | null {
  if (!price || !variant || !year || Object.keys(rangeMap).length === 0) return null
  const variantKey = Object.keys(rangeMap).find(k => k.toLowerCase() === variant.toLowerCase())
  if (!variantKey) return null
  const cell = rangeMap[variantKey]?.[String(year)]
  if (!cell || !cell.avg || cell.count < 3) return null
  const pct = ((price - cell.avg) / cell.avg) * 100
  if (pct <= -15) return { pct, label: 'deal',               pillCls: 'bg-emerald-900/80 text-emerald-300 border border-emerald-800/60', borderCls: 'border-l-emerald-500' }
  if (pct <=  -5) return { pct, label: `${Math.round(-pct)}% below`, pillCls: 'bg-green-900/60 text-green-300 border border-green-800/50',   borderCls: 'border-l-green-600' }
  if (pct <=   5) return { pct, label: 'fair',               pillCls: 'bg-slate-800 text-slate-500 border border-slate-700',                borderCls: 'border-l-slate-800' }
  if (pct <=  15) return { pct, label: `${Math.round(pct)}% above`,  pillCls: 'bg-amber-900/60 text-amber-300 border border-amber-800/50',   borderCls: 'border-l-amber-700' }
  return               { pct, label: 'high',               pillCls: 'bg-red-900/60 text-red-300 border border-red-800/50',             borderCls: 'border-l-red-700' }
}

function daysAgo(dateStr: string | null): string | null {
  if (!dateStr) return null
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86_400_000)
  if (diff === 0) return 'today'
  if (diff === 1) return '1d ago'
  return `${diff}d ago`
}

// ── Autocomplete input ────────────────────────────────────────────────────────

function AutocompleteInput({
  value, onChange, placeholder, options,
}: {
  value: string; onChange: (v: string) => void; placeholder: string; options: string[]
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const filtered = options.filter(o => o.toLowerCase().includes(value.toLowerCase()))

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="relative">
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-slate-500 placeholder:text-slate-600"
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-50 top-full left-0 right-0 mt-0.5 bg-slate-800 border border-slate-700 rounded shadow-xl max-h-40 overflow-auto">
          {filtered.slice(0, 20).map(o => (
            <li
              key={o}
              onMouseDown={() => { onChange(o); setOpen(false) }}
              className="px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-700 cursor-pointer"
            >
              {o}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Listing panel ─────────────────────────────────────────────────────────────

interface PatchBody {
  variant?: string
  year?: number
  km_driven?: number
  price?: number
  fuel_type?: string
  transmission?: string
  location_city?: string
  description?: string
}

function ListingPanel({
  listing,
  groupListingIds,
  onClose,
  onUpdated,
  onShortlistToggle,
}: {
  listing: Listing
  groupListingIds?: string[]
  onClose: () => void
  onUpdated: (updated: Listing) => void
  onShortlistToggle: (l: Listing) => void
}) {
  const [activeListing, setActiveListing] = useState<Listing>(listing)
  const [groupListings, setGroupListings] = useState<Listing[]>([])
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<PatchBody>({
    variant: listing.variant_canonical ?? listing.variant ?? '',
    year: listing.year ?? undefined,
    km_driven: listing.km_driven ?? undefined,
    price: listing.price ?? undefined,
    fuel_type: listing.fuel_type ?? '',
    transmission: listing.transmission ?? '',
    location_city: listing.location_city ?? '',
    description: listing.description ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [fairValue, setFairValue] = useState<FairValueData | null>(null)

  // Reset when parent opens a new listing
  useEffect(() => {
    setActiveListing(listing)
    setGroupListings([])
    setEditing(false)
  }, [listing.id])

  // Sync form and fair value when active listing changes
  useEffect(() => {
    setForm({
      variant: activeListing.variant_canonical ?? activeListing.variant ?? '',
      year: activeListing.year ?? undefined,
      km_driven: activeListing.km_driven ?? undefined,
      price: activeListing.price ?? undefined,
      fuel_type: activeListing.fuel_type ?? '',
      transmission: activeListing.transmission ?? '',
      location_city: activeListing.location_city ?? '',
      description: activeListing.description ?? '',
    })
    setEditing(false)

    const variant = activeListing.variant_canonical ?? activeListing.variant
    const { make, model, year } = activeListing
    if (!make || !model || !variant || !year) { setFairValue(null); return }
    const p = new URLSearchParams({ make, model, variant, year: String(year) })
    fetch(`/api/stats/fair-value?${p}`)
      .then(r => r.json())
      .then(setFairValue)
      .catch(() => setFairValue(null))
  }, [activeListing.id])

  // Fetch all listings in the dedup group so vendor switcher has prices+sources
  useEffect(() => {
    if (!groupListingIds || groupListingIds.length <= 1) { setGroupListings([]); return }
    Promise.all(groupListingIds.map(id => fetch(`/api/listings/${id}`).then(r => r.json())))
      .then(results => {
        // sort cheapest first
        setGroupListings(results.sort((a: Listing, b: Listing) => (a.price ?? 0) - (b.price ?? 0)))
      })
      .catch(() => {})
  }, [groupListingIds?.join(',')])

  const save = async () => {
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {}
      if (form.variant !== undefined)      payload.variant       = form.variant || null
      if (form.year !== undefined)         payload.year          = form.year || null
      if (form.km_driven !== undefined)    payload.km_driven     = form.km_driven || null
      if (form.price !== undefined)        payload.price         = form.price || null
      if (form.fuel_type !== undefined)    payload.fuel_type     = form.fuel_type || null
      if (form.transmission !== undefined) payload.transmission  = form.transmission || null
      if (form.location_city !== undefined) payload.location_city = form.location_city || null
      if (form.description !== undefined)  payload.description   = form.description || null

      const res: Listing = await fetch(`/api/listings/${activeListing.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then(r => r.json())
      setActiveListing(res)
      onUpdated(res)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const displayVariant = activeListing.variant  // raw scraped name — shown to user
  const km = kmHealth(activeListing.km_driven, activeListing.year)
  const cheapestPrice = groupListings.length > 0
    ? Math.min(...groupListings.map(g => g.price ?? Infinity))
    : null

  const Field = ({ label, value }: { label: string; value: string | null | undefined }) => (
    <div className="grid grid-cols-[7rem_1fr] items-start gap-1 py-1.5 border-b border-slate-800/50 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xs text-slate-200 break-words">{value || '—'}</span>
    </div>
  )

  const EditField = ({ label, field, type = 'text' }: { label: string; field: keyof PatchBody; type?: string }) => (
    <div className="grid grid-cols-[7rem_1fr] items-center gap-1 py-1.5 border-b border-slate-800/50 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <input
        type={type}
        value={(form[field] as string | number | undefined) ?? ''}
        onChange={e => setForm(f => ({ ...f, [field]: type === 'number' ? (e.target.value ? +e.target.value : undefined) : e.target.value }))}
        className="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-xs text-slate-200 outline-none focus:border-slate-500 w-full"
      />
    </div>
  )

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-[28rem] z-50 bg-[#0d1117] border-l border-slate-800 shadow-2xl flex flex-col overflow-hidden">

        {/* Vendor switcher — shown only for deduped groups with >1 source */}
        {groupListings.length > 1 && (
          <div className="px-3 py-2 border-b border-slate-800 bg-slate-900/60 flex gap-1.5 overflow-x-auto">
            {groupListings.map(gl => {
              const isActive = activeListing.id === gl.id
              const priceDiff = cheapestPrice !== null && gl.price !== null && gl.price > cheapestPrice
                ? gl.price - cheapestPrice
                : null
              return (
                <button
                  key={gl.id}
                  onClick={() => setActiveListing(gl)}
                  className={`flex-shrink-0 flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors ${
                    isActive ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                  }`}
                >
                  <span className={`text-[10px] px-1 py-0.5 rounded font-medium ${SOURCE_COLORS[gl.source] ?? 'bg-slate-700 text-slate-300'}`}>
                    {gl.source}
                  </span>
                  <span className="font-mono text-[11px]">{fmt_price(gl.price)}</span>
                  {priceDiff !== null && (
                    <span className="text-slate-600 text-[10px]">+{fmt_price(priceDiff)}</span>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {/* Header */}
        <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-slate-800">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <a
                href={activeListing.url}
                target="_blank"
                rel="noreferrer"
                className="text-slate-100 font-medium text-sm hover:text-white"
              >
                {activeListing.make} {activeListing.model} {activeListing.year}
              </a>
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${SOURCE_COLORS[activeListing.source] ?? 'bg-slate-700 text-slate-300'}`}>
                {activeListing.source}
              </span>
              {activeListing.is_manually_edited && (
                <span className="text-xs text-amber-500/80">✎ edited</span>
              )}
            </div>
            {displayVariant && (
              <div className="text-xs text-slate-400 mt-0.5 truncate" title={displayVariant}>
                {displayVariant}
              </div>
            )}
            {activeListing.variant_canonical && activeListing.variant_canonical !== activeListing.variant && (
              <div className="text-[10px] text-slate-600 mt-0.5">≈ {activeListing.variant_canonical}</div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => onShortlistToggle(activeListing)}
              className={`text-lg leading-none transition-colors ${activeListing.shortlisted ? 'text-amber-400 hover:text-amber-300' : 'text-slate-600 hover:text-slate-400'}`}
            >
              {activeListing.shortlisted ? '★' : '☆'}
            </button>
            <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none px-1">×</button>
          </div>
        </div>

        {/* Images */}
        {activeListing.images && activeListing.images.length > 0 && (
          <div className="flex gap-1.5 px-4 py-2 overflow-x-auto">
            {activeListing.images.slice(0, 5).map((img, i) => (
              <img key={i} src={img} alt="" className="h-20 w-32 object-cover rounded flex-shrink-0 bg-slate-800" />
            ))}
          </div>
        )}

        {/* Price + fair value */}
        <div className="px-4 py-3 border-b border-slate-800">
          <span className="text-2xl font-mono font-bold text-white">{fmt_price(activeListing.price)}</span>
          {fairValue && fairValue.sample_size >= 5 && fairValue.fair_value !== null && (
            <div className="mt-1.5 space-y-0.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-slate-500">Market rate</span>
                <span className="text-sm font-mono text-slate-300">{fmt_price(fairValue.fair_value)}</span>
                <span className="text-xs text-slate-600">
                  {fairValue.sample_size} cars · {fairValue.inactive_count} sold
                </span>
              </div>
              {fairValue.p25 !== null && fairValue.p75 !== null && (
                <div className="text-[11px] text-slate-600 font-mono">
                  p25 {fmt_price(fairValue.p25)} – p75 {fmt_price(fairValue.p75)}
                </div>
              )}
            </div>
          )}
          {fairValue && fairValue.sample_size > 0 && fairValue.sample_size < 5 && (
            <div className="mt-1 text-xs text-slate-600">Market rate · low data ({fairValue.sample_size} cars)</div>
          )}
        </div>

        {/* KM health in panel */}
        {km && (
          <div className="px-4 py-1.5 border-b border-slate-800 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${km.dot} flex-shrink-0`} />
            <span className="text-xs text-slate-500">{km.title}</span>
          </div>
        )}

        {/* Fields */}
        <div className="flex-1 overflow-y-auto px-4 py-2">
          {editing ? (
            <div className="space-y-0">
              <EditField label="Variant" field="variant" />
              <EditField label="Year" field="year" type="number" />
              <EditField label="KM driven" field="km_driven" type="number" />
              <EditField label="Price (₹)" field="price" type="number" />
              <EditField label="Fuel type" field="fuel_type" />
              <EditField label="Transmission" field="transmission" />
              <EditField label="City" field="location_city" />
              <div className="py-1">
                <label className="text-xs text-slate-500 block mb-1">Description</label>
                <textarea
                  value={form.description ?? ''}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  rows={3}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 outline-none focus:border-slate-500 resize-none"
                />
              </div>
            </div>
          ) : (
            <div>
              <Field label="Variant" value={displayVariant} />
              <Field label="Year" value={activeListing.year?.toString()} />
              <Field label="KM driven" value={fmt_km(activeListing.km_driven)} />
              <Field label="Fuel" value={activeListing.fuel_type} />
              <Field label="Transmission" value={activeListing.transmission} />
              <Field label="City" value={activeListing.location_city} />
              <Field label="State" value={activeListing.location_state} />
              <Field label="Seller" value={activeListing.seller_type} />
              {activeListing.description && (
                <div className="mt-2">
                  <div className="text-xs text-slate-500 mb-1">Description</div>
                  <p className="text-xs text-slate-400 leading-relaxed">{activeListing.description}</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-slate-800 flex gap-2">
          {editing ? (
            <>
              <button
                onClick={save}
                disabled={saving}
                className="bg-slate-600 hover:bg-slate-500 disabled:opacity-40 text-slate-100 text-xs px-3 py-1.5 rounded"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => setEditing(false)} className="text-slate-400 hover:text-slate-200 text-xs px-3 py-1.5">Cancel</button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditing(true)}
                className="bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs px-3 py-1.5 rounded"
              >
                Edit details
              </button>
              <a
                href={activeListing.url}
                target="_blank"
                rel="noreferrer"
                className="text-slate-400 hover:text-slate-200 text-xs px-3 py-1.5"
              >
                Open listing ↗
              </a>
            </>
          )}
        </div>
      </div>
    </>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Listings() {
  const [mode, setMode] = useState<'all' | 'deduped'>('all')
  const [listings, setListings] = useState<Listing[]>([])
  const [groups, setGroups] = useState<DedupGroup[]>([])
  const [filters, setFilters] = useState<Filters>(INIT_FILTERS)
  const [searchQ, setSearchQ] = useState('')
  const debouncedQ = useDebounce(searchQ, 300)
  const [loading, setLoading] = useState(false)
  const [options, setOptions] = useState<Options>({ variants: [], cities: [], fuel_types: [], transmissions: [] })
  const [selected, setSelected] = useState<Listing | null>(null)
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[] | null>(null)
  const [carConfigs, setCarConfigs] = useState<CarConfig[]>([])
  const [priceRangeMap, setPriceRangeMap] = useState<PriceRangeMap>({})

  const setF = (k: keyof Filters, v: string) => setFilters(f => ({ ...f, [k]: v }))
  const selectedConfig = carConfigs.find(c => c.id === filters.config_id) ?? null

  const loadOptions = useCallback((configId = filters.config_id) => {
    const cfg = carConfigs.find(c => c.id === configId) ?? null
    const p = new URLSearchParams()
    if (cfg) { p.set('make', cfg.make); p.set('model', cfg.model) }
    fetch(`/api/listings/options?${p}`)
      .then(r => r.json())
      .then(setOptions)
      .catch(() => {})
  }, [filters.config_id, carConfigs])

  useEffect(() => {
    fetch('/api/configs/')
      .then(r => r.json())
      .then((cfgs: CarConfig[]) => setCarConfigs(cfgs))
      .catch(() => {})
  }, [])

  useEffect(() => { loadOptions() }, [loadOptions])

  // Fetch price-range for deal score computation when config changes
  useEffect(() => {
    const cfg = carConfigs.find(c => c.id === filters.config_id)
    if (!cfg) { setPriceRangeMap({}); return }
    fetch(`/api/stats/price-range?make=${encodeURIComponent(cfg.make)}&model=${encodeURIComponent(cfg.model)}`)
      .then(r => r.json())
      .then(setPriceRangeMap)
      .catch(() => setPriceRangeMap({}))
  }, [filters.config_id, carConfigs])

  const load = useCallback((currentMode = mode, q = debouncedQ) => {
    setLoading(true)
    const p = new URLSearchParams()
    if (filters.config_id) p.set('config_id', filters.config_id)
    if (filters.city) p.set('city', filters.city)
    if (filters.variant) p.set('variant', filters.variant)
    if (filters.year_min) p.set('year_min', filters.year_min)
    if (filters.year_max) p.set('year_max', filters.year_max)
    if (filters.price_min) p.set('price_min', filters.price_min)
    if (filters.price_max) p.set('price_max', filters.price_max)
    if (filters.km_max) p.set('km_max', filters.km_max)
    if (q) p.set('q', q)
    p.set('limit', '300')

    if (currentMode === 'deduped') {
      fetch(`/api/listings/deduped?${p}`)
        .then(r => r.json())
        .then(setGroups)
        .finally(() => setLoading(false))
    } else {
      if (filters.source) p.set('source', filters.source)
      if (filters.fuel_type) p.set('fuel_type', filters.fuel_type)
      if (filters.transmission) p.set('transmission', filters.transmission)
      p.set('sort_by', filters.sort_by)
      p.set('sort_dir', filters.sort_dir)
      fetch(`/api/listings/?${p}`)
        .then(r => r.json())
        .then(setListings)
        .finally(() => setLoading(false))
    }
  }, [mode, filters, debouncedQ])

  const switchMode = (m: 'all' | 'deduped') => { setMode(m); load(m, debouncedQ) }

  useEffect(() => { load() }, [debouncedQ])

  const handleListingUpdated = (updated: Listing) => {
    setListings(ls => ls.map(l => l.id === updated.id ? updated : l))
    setGroups(gs => gs.map(g => ({
      ...g,
      representative: g.representative.id === updated.id ? updated : g.representative,
    })))
    setSelected(updated)
    loadOptions()
  }

  const toggleShortlist = async (l: Listing) => {
    if (l.shortlisted) {
      await fetch(`/api/shortlist/${l.id}`, { method: 'DELETE' })
    } else {
      await fetch(`/api/shortlist/${l.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    }
    const updated = { ...l, shortlisted: !l.shortlisted }
    handleListingUpdated(updated)
  }

  const count = mode === 'deduped' ? groups.length : listings.length
  const isEmpty = count === 0 && !loading

  return (
    <div className="space-y-3">
      {/* Mode toggle */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-0.5 bg-slate-900 border border-slate-800 rounded-lg p-1">
          {(['all', 'deduped'] as const).map(m => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className={`px-3 py-1 rounded text-xs transition-colors ${mode === m ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200'}`}
            >
              {m === 'all' ? 'All listings' : 'Unique cars'}
            </button>
          ))}
        </div>
        <span className={`text-xs font-mono ${count > 0 ? 'text-slate-300' : 'text-slate-600'}`}>
          {loading ? 'loading…' : `${count} ${mode === 'deduped' ? 'unique cars' : 'listings'}`}
        </span>
      </div>

      {/* Search bar */}
      <div className="relative">
        <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none">
          <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <input
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          placeholder="Search make, model, variant, city…"
          className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 outline-none focus:border-slate-500 placeholder:text-slate-600"
        />
        {searchQ && (
          <button onClick={() => setSearchQ('')} className="absolute inset-y-0 right-3 flex items-center text-slate-500 hover:text-slate-300">×</button>
        )}
      </div>

      {/* Filters */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-3">
        <div>
          <label className="text-xs text-slate-500 mb-1 block">Car</label>
          <select
            value={filters.config_id}
            onChange={e => { setF('config_id', e.target.value); setF('variant', ''); loadOptions(e.target.value) }}
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-slate-500"
          >
            <option value="">All cars</option>
            {carConfigs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-4 gap-3">
          <div className={mode === 'deduped' ? 'opacity-30 pointer-events-none' : ''}>
            <label className="text-xs text-slate-500 mb-1 block">Source</label>
            <AutocompleteInput
              value={filters.source} onChange={v => setF('source', v)}
              placeholder="cardekho / olx…"
              options={['cardekho', 'cars24', 'carwale', 'olx', 'spinny', 'cartrade']}
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">City</label>
            <AutocompleteInput value={filters.city} onChange={v => setF('city', v)} placeholder="Chennai…" options={options.cities} />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">
              Variant{selectedConfig ? ` (${selectedConfig.model})` : ''}
            </label>
            <select
              value={filters.variant}
              onChange={e => setF('variant', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-slate-500"
            >
              <option value="">All variants</option>
              {options.variants.map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className={mode === 'deduped' ? 'opacity-30 pointer-events-none' : ''}>
            <label className="text-xs text-slate-500 mb-1 block">Fuel</label>
            <AutocompleteInput value={filters.fuel_type} onChange={v => setF('fuel_type', v)} placeholder="Petrol / Diesel" options={options.fuel_types} />
          </div>
        </div>

        <div className="grid grid-cols-6 gap-3">
          {[
            { label: 'Year from', key: 'year_min' as const, placeholder: '2018' },
            { label: 'Year to',   key: 'year_max' as const, placeholder: '2023' },
            { label: 'Price min (₹)', key: 'price_min' as const, placeholder: '3,00,000' },
            { label: 'Price max (₹)', key: 'price_max' as const, placeholder: '9,00,000' },
            { label: 'KM max', key: 'km_max' as const, placeholder: '80,000' },
          ].map(({ label, key, placeholder }) => (
            <div key={key}>
              <label className="text-xs text-slate-500 mb-1 block">{label}</label>
              <input
                type="number" value={filters[key]} onChange={e => setF(key, e.target.value)}
                placeholder={placeholder}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-slate-500 placeholder:text-slate-600"
              />
            </div>
          ))}
          <div className={mode === 'deduped' ? 'opacity-30 pointer-events-none' : ''}>
            <label className="text-xs text-slate-500 mb-1 block">Transmission</label>
            <AutocompleteInput value={filters.transmission} onChange={v => setF('transmission', v)} placeholder="Manual…" options={options.transmissions} />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-0.5">
          <div className={`flex items-center gap-1.5 ${mode === 'deduped' ? 'opacity-30 pointer-events-none' : ''}`}>
            <label className="text-xs text-slate-500">Sort</label>
            <select value={filters.sort_by} onChange={e => setF('sort_by', e.target.value)} className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 outline-none">
              {['price', 'km_driven', 'year', 'scraped_at', 'last_seen_at'].map(v => <option key={v} value={v}>{v.replace('_', ' ')}</option>)}
            </select>
            <select value={filters.sort_dir} onChange={e => setF('sort_dir', e.target.value)} className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 outline-none">
              <option value="asc">↑ asc</option>
              <option value="desc">↓ desc</option>
            </select>
          </div>
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => { setFilters(INIT_FILTERS); setSearchQ(''); loadOptions('') }}
              className="text-slate-500 hover:text-slate-300 text-xs px-2 py-1.5"
            >
              reset
            </button>
            <button onClick={() => load()} className="bg-slate-600 hover:bg-slate-500 text-slate-100 text-xs px-4 py-1.5 rounded">
              {loading ? 'Loading…' : 'Apply'}
            </button>
          </div>
        </div>
      </div>

      {/* Empty state */}
      {isEmpty && (
        <div className="text-slate-500 text-sm text-center py-16 border border-dashed border-slate-800 rounded-lg">
          No listings. Create a search config and hit "scrape" to fetch results.
        </div>
      )}

      {/* All listings */}
      {mode === 'all' && !isEmpty && (
        <div className="rounded-lg border border-slate-800 divide-y divide-slate-800/40 overflow-hidden">
          {listings.map((l, i) => {
            const displayVariant = l.variant  // raw scraped name
            const analysisVariant = l.variant_canonical ?? l.variant  // canonical for deal score
            const km = kmHealth(l.km_driven, l.year)
            const deal = dealScore(l.price, analysisVariant, l.year, priceRangeMap)
            const age = daysAgo(l.scraped_at)
            const borderCls = deal?.borderCls ?? 'border-l-transparent'
            return (
              <div
                key={l.id}
                onClick={() => { setSelected(l); setSelectedGroupIds(null) }}
                className={`flex items-center gap-4 px-4 py-3 border-l-2 ${borderCls} cursor-pointer transition-colors hover:bg-slate-800/50 ${
                  i % 2 === 0 ? '' : 'bg-slate-900/20'
                } ${selected?.id === l.id ? 'bg-slate-800/60' : ''}`}
              >
                {/* Left: car info */}
                <div className="flex-1 min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-100 font-medium text-sm">{l.make} {l.model}</span>
                    {l.year && <span className="text-xs text-slate-500 font-mono">{l.year}</span>}
                    {deal && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium leading-none ${deal.pillCls}`}>
                        {deal.label}
                      </span>
                    )}
                    {l.is_manually_edited && <span className="text-[10px] text-amber-600/60">✎</span>}
                  </div>
                  {displayVariant && (
                    <div className="text-xs text-slate-400 truncate" title={displayVariant}>{displayVariant}</div>
                  )}
                  <div className="flex items-center gap-2 text-xs text-slate-500 flex-wrap pt-0.5">
                    <span className="flex items-center gap-1">
                      {km && <span className={`w-1.5 h-1.5 rounded-full ${km.dot} flex-shrink-0`} title={km.title} />}
                      <span className="font-mono">{fmt_km(l.km_driven)}</span>
                    </span>
                    {l.fuel_type && <><span className="text-slate-700">·</span><span>{l.fuel_type}</span></>}
                    {l.transmission && <><span className="text-slate-700">·</span><span>{l.transmission}</span></>}
                    {l.location_city && <><span className="text-slate-700">·</span><span>{l.location_city}</span></>}
                  </div>
                </div>

                {/* Right: price + source */}
                <div className="flex-shrink-0 text-right space-y-1">
                  <div className="text-base font-mono font-bold text-white">{fmt_price(l.price)}</div>
                  <div className="flex items-center justify-end gap-1.5">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${SOURCE_COLORS[l.source] ?? 'bg-slate-700 text-slate-300'}`}>
                      {l.source}
                    </span>
                    {age && <span className="text-[10px] text-slate-600">{age}</span>}
                  </div>
                </div>

                {/* Star */}
                <button
                  onClick={e => { e.stopPropagation(); toggleShortlist(l) }}
                  className={`flex-shrink-0 text-base leading-none transition-colors ${l.shortlisted ? 'text-amber-400 hover:text-amber-300' : 'text-slate-700 hover:text-slate-400'}`}
                >
                  {l.shortlisted ? '★' : '☆'}
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Deduped */}
      {mode === 'deduped' && !isEmpty && (
        <div className="rounded-lg border border-slate-800 divide-y divide-slate-800/40 overflow-hidden">
          {groups.map((g, i) => {
            const rep = g.representative
            const displayVariant = rep.variant  // raw scraped name
            const analysisVariant = rep.variant_canonical ?? rep.variant  // canonical for deal score
            const km = kmHealth(rep.km_driven, rep.year)
            const deal = dealScore(g.best_price, analysisVariant, rep.year, priceRangeMap)
            const borderCls = deal?.borderCls ?? 'border-l-transparent'
            return (
              <div
                key={g.dedup_key}
                onClick={() => { setSelected(rep); setSelectedGroupIds(g.listing_ids) }}
                className={`flex items-center gap-4 px-4 py-3 border-l-2 ${borderCls} cursor-pointer transition-colors hover:bg-slate-800/50 ${
                  i % 2 === 0 ? '' : 'bg-slate-900/20'
                } ${selected?.id === rep.id ? 'bg-slate-800/60' : ''}`}
              >
                <div className="flex-1 min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-100 font-medium text-sm">{rep.make} {rep.model}</span>
                    {rep.year && <span className="text-xs text-slate-500 font-mono">{rep.year}</span>}
                    {deal && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium leading-none ${deal.pillCls}`}>
                        {deal.label}
                      </span>
                    )}
                  </div>
                  {displayVariant && (
                    <div className="text-xs text-slate-400 truncate" title={displayVariant}>{displayVariant}</div>
                  )}
                  <div className="flex items-center gap-2 text-xs text-slate-500 flex-wrap pt-0.5">
                    <span className="flex items-center gap-1">
                      {km && <span className={`w-1.5 h-1.5 rounded-full ${km.dot} flex-shrink-0`} title={km.title} />}
                      <span className="font-mono">{fmt_km(rep.km_driven)}</span>
                    </span>
                    {rep.fuel_type && <><span className="text-slate-700">·</span><span>{rep.fuel_type}</span></>}
                    {rep.location_city && <><span className="text-slate-700">·</span><span>{rep.location_city}</span></>}
                    <span className="text-slate-700">·</span>
                    <div className="flex items-center gap-1">
                      {g.sources.map(s => (
                        <span key={s} className={`text-[10px] px-1 py-0.5 rounded font-medium ${SOURCE_COLORS[s] ?? 'bg-slate-700 text-slate-300'}`}>
                          {s}
                        </span>
                      ))}
                      {g.listing_ids.length > 1 && (
                        <span className="text-[10px] px-1 py-0.5 rounded bg-slate-800 text-slate-500 border border-slate-700/50">
                          {g.listing_ids.length}×
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex-shrink-0 text-right">
                  <div className="text-base font-mono font-bold text-white">{fmt_price(g.best_price)}</div>
                </div>

                <button
                  onClick={e => { e.stopPropagation(); toggleShortlist(rep) }}
                  className={`flex-shrink-0 text-base leading-none transition-colors ${rep.shortlisted ? 'text-amber-400 hover:text-amber-300' : 'text-slate-700 hover:text-slate-400'}`}
                >
                  {rep.shortlisted ? '★' : '☆'}
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Detail panel */}
      {selected && (
        <ListingPanel
          listing={selected}
          groupListingIds={selectedGroupIds ?? undefined}
          onClose={() => setSelected(null)}
          onUpdated={handleListingUpdated}
          onShortlistToggle={toggleShortlist}
        />
      )}
    </div>
  )
}

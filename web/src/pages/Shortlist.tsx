import { useEffect, useState } from 'react'

interface Listing {
  id: string
  source: string
  url: string
  make: string | null
  model: string | null
  variant: string | null
  year: number | null
  km_driven: number | null
  fuel_type: string | null
  transmission: string | null
  price: number | null
  location_city: string | null
  location_state: string | null
  seller_type: string | null
  scraped_at: string | null
  shortlisted: boolean
}

interface ShortlistEntry {
  listing_id: string
  notes: string
  added_at: string
}

interface Item {
  entry: ShortlistEntry
  listing: Listing | null
}

function fmt_price(p: number | null) {
  if (!p) return '—'
  if (p >= 10_000_000) return `₹${(p / 10_000_000).toFixed(2)} Cr`
  return `₹${(p / 100_000).toFixed(2)} L`
}

function fmt_km(km: number | null) {
  if (!km) return '—'
  return `${km.toLocaleString('en-IN')} km`
}

const SOURCE_COLORS: Record<string, string> = {
  cardekho: 'bg-orange-900 text-orange-300',
  carwale: 'bg-blue-900 text-blue-300',
  cars24: 'bg-green-900 text-green-300',
  olx: 'bg-purple-900 text-purple-300',
}

const COMPARE_FIELDS: { label: string; render: (l: Listing) => string | null }[] = [
  { label: 'Price', render: l => fmt_price(l.price) },
  { label: 'Year', render: l => l.year?.toString() ?? '—' },
  { label: 'Mileage', render: l => fmt_km(l.km_driven) },
  { label: 'Variant', render: l => l.variant || '—' },
  { label: 'Fuel', render: l => l.fuel_type || '—' },
  { label: 'Transmission', render: l => l.transmission || '—' },
  { label: 'City', render: l => l.location_city || '—' },
  { label: 'Seller', render: l => l.seller_type || '—' },
  { label: 'Source', render: l => l.source },
]

export default function Shortlist() {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [editingNotes, setEditingNotes] = useState<string | null>(null)
  const [notesValue, setNotesValue] = useState('')

  const load = () => {
    setLoading(true)
    fetch('/api/shortlist/')
      .then(r => r.json())
      .then(async (entries: ShortlistEntry[]) => {
        const fetched = await Promise.all(
          entries.map(async e => {
            try {
              const l = await fetch(`/api/listings/${e.listing_id}`).then(r => r.json())
              return { entry: e, listing: l as Listing }
            } catch {
              return { entry: e, listing: null }
            }
          })
        )
        setItems(fetched)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const remove = async (id: string) => {
    await fetch(`/api/shortlist/${id}`, { method: 'DELETE' })
    setItems(prev => prev.filter(i => i.entry.listing_id !== id))
    setSelected(prev => { const s = new Set(prev); s.delete(id); return s })
  }

  const saveNotes = async (id: string) => {
    await fetch(`/api/shortlist/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: notesValue }),
    })
    setItems(prev => prev.map(i =>
      i.entry.listing_id === id ? { ...i, entry: { ...i.entry, notes: notesValue } } : i
    ))
    setEditingNotes(null)
  }

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const s = new Set(prev)
      if (s.has(id)) {
        s.delete(id)
      } else if (s.size < 4) {
        s.add(id)
      }
      return s
    })
  }

  const compareItems = items.filter(i => selected.has(i.entry.listing_id) && i.listing)

  if (loading) {
    return <div className="text-slate-500 text-sm py-8 text-center">Loading…</div>
  }

  if (items.length === 0) {
    return (
      <div className="text-slate-500 text-sm text-center py-16 border border-dashed border-slate-800 rounded-lg">
        No cars shortlisted yet. Click ☆ on any listing to save it here.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-500">
          {items.length} shortlisted · select up to 4 to compare
        </div>
        {selected.size > 0 && (
          <button
            onClick={() => setSelected(new Set())}
            className="text-xs text-slate-500 hover:text-slate-300"
          >
            clear selection
          </button>
        )}
      </div>

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {items.map(({ entry, listing }) => {
          const isSelected = selected.has(entry.listing_id)
          const isEditing = editingNotes === entry.listing_id

          return (
            <div
              key={entry.listing_id}
              className={`bg-slate-900 border rounded-lg p-4 space-y-3 transition-colors cursor-pointer ${
                isSelected
                  ? 'border-slate-500 ring-1 ring-slate-500'
                  : 'border-slate-800 hover:border-slate-700'
              }`}
              onClick={() => toggleSelect(entry.listing_id)}
            >
              {listing ? (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <a
                        href={listing.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-slate-200 hover:text-white font-medium text-sm"
                        onClick={e => e.stopPropagation()}
                      >
                        {listing.make} {listing.model}
                      </a>
                      <div className="text-xs text-slate-500 mt-0.5">{listing.variant || '—'}</div>
                    </div>
                    <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${SOURCE_COLORS[listing.source] ?? 'bg-slate-700 text-slate-300'}`}>
                      {listing.source}
                    </span>
                  </div>

                  <div className="text-lg font-mono font-semibold text-slate-100">
                    {fmt_price(listing.price)}
                  </div>

                  <div className="grid grid-cols-2 gap-1 text-xs">
                    <div className="text-slate-500">Year</div>
                    <div className="text-slate-300">{listing.year ?? '—'}</div>
                    <div className="text-slate-500">KM</div>
                    <div className="text-slate-300 font-mono">{fmt_km(listing.km_driven)}</div>
                    <div className="text-slate-500">Fuel</div>
                    <div className="text-slate-300">{listing.fuel_type || '—'}</div>
                    <div className="text-slate-500">Trans.</div>
                    <div className="text-slate-300">{listing.transmission || '—'}</div>
                    <div className="text-slate-500">City</div>
                    <div className="text-slate-300">{listing.location_city || '—'}</div>
                  </div>
                </>
              ) : (
                <div className="text-slate-600 text-xs">Listing not found</div>
              )}

              {/* Notes */}
              <div onClick={e => e.stopPropagation()}>
                {isEditing ? (
                  <div className="space-y-1">
                    <textarea
                      autoFocus
                      value={notesValue}
                      onChange={e => setNotesValue(e.target.value)}
                      rows={2}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 outline-none focus:border-slate-500 resize-none"
                      placeholder="Notes…"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => saveNotes(entry.listing_id)}
                        className="text-xs text-slate-300 hover:text-white"
                      >
                        save
                      </button>
                      <button
                        onClick={() => setEditingNotes(null)}
                        className="text-xs text-slate-600 hover:text-slate-400"
                      >
                        cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    className="text-xs text-slate-600 hover:text-slate-400 cursor-text min-h-[1.5rem] italic"
                    onClick={() => {
                      setEditingNotes(entry.listing_id)
                      setNotesValue(entry.notes)
                    }}
                  >
                    {entry.notes || 'Add notes…'}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between pt-1" onClick={e => e.stopPropagation()}>
                <div className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                  isSelected
                    ? 'border-slate-500 bg-slate-700 text-slate-200'
                    : 'border-slate-700 text-slate-600'
                }`}>
                  {isSelected ? '✓ comparing' : 'compare'}
                </div>
                <button
                  onClick={() => remove(entry.listing_id)}
                  className="text-xs text-slate-700 hover:text-red-400 transition-colors"
                >
                  remove
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Comparison table */}
      {compareItems.length >= 2 && (
        <div className="space-y-2">
          <div className="text-xs text-slate-500 pt-2">Comparing {compareItems.length} cars</div>
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900/60">
                  <th className="text-left px-3 py-2 font-normal text-slate-500 w-28">Field</th>
                  {compareItems.map(({ listing }) => listing && (
                    <th key={listing.id} className="text-left px-3 py-2 font-normal">
                      <a
                        href={listing.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-slate-200 hover:text-white"
                      >
                        {listing.make} {listing.model} {listing.year}
                      </a>
                      <div className={`mt-0.5 text-xs px-1.5 py-0.5 rounded w-fit ${SOURCE_COLORS[listing.source] ?? 'bg-slate-700 text-slate-300'}`}>
                        {listing.source}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE_FIELDS.map(({ label, render }, fi) => (
                  <tr
                    key={label}
                    className={`border-b border-slate-800/50 ${fi % 2 === 0 ? 'bg-transparent' : 'bg-slate-900/20'}`}
                  >
                    <td className="px-3 py-2 text-slate-500 font-medium">{label}</td>
                    {compareItems.map(({ listing }) => {
                      if (!listing) return <td key="null" />
                      const val = render(listing)
                      const isPrice = label === 'Price'
                      const allPrices = isPrice
                        ? compareItems.map(i => i.listing?.price ?? Infinity)
                        : []
                      const minPrice = isPrice ? Math.min(...allPrices) : null
                      const highlight = isPrice && listing.price === minPrice
                      return (
                        <td
                          key={listing.id}
                          className={`px-3 py-2 font-mono ${highlight ? 'text-emerald-400 font-semibold' : 'text-slate-300'}`}
                        >
                          {val}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                {/* Notes row */}
                <tr className="border-b border-slate-800/50">
                  <td className="px-3 py-2 text-slate-500 font-medium">Notes</td>
                  {compareItems.map(({ entry }) => (
                    <td key={entry.listing_id} className="px-3 py-2 text-slate-500 italic">
                      {entry.notes || '—'}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

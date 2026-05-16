import { useState } from 'react'
import Listings from './pages/Listings'
import SearchConfigs from './pages/SearchConfigs'
import Stats from './pages/Stats'
import Shortlist from './pages/Shortlist'

type Tab = 'listings' | 'configs' | 'stats' | 'shortlist'

const TAB_LABELS: Record<Tab, string> = {
  listings: 'Listings',
  configs: 'Searches',
  stats: 'Market',
  shortlist: 'Saved',
}

export default function App() {
  const [tab, setTab] = useState<Tab>('listings')

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-200">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center gap-6">
        <span className="text-slate-500 font-mono text-sm tracking-widest">scrapper</span>
        <nav className="flex gap-1">
          {(Object.keys(TAB_LABELS) as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${
                tab === t
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </nav>
      </header>

      <main className="p-6">
        {tab === 'listings' && <Listings />}
        {tab === 'configs' && <SearchConfigs />}
        {tab === 'stats' && <Stats />}
        {tab === 'shortlist' && <Shortlist />}
      </main>
    </div>
  )
}

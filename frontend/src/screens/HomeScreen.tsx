import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SearchBar from '../components/SearchBar'
import { bookmarkStore, historyStore } from '../stores/db'

interface Shortcut {
  title: string
  url: string
  icon: string
}

export default function HomeScreen() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([])

  useEffect(() => {
    loadShortcuts()
  }, [])

  async function loadShortcuts() {
    const bookmarks = await bookmarkStore.list()
    const recent = await historyStore.list(8)
    const items: Shortcut[] = []
    const seen = new Set<string>()
    for (const b of bookmarks.slice(0, 4)) {
      if (seen.has(b.url)) continue
      seen.add(b.url)
      items.push({ title: b.title, url: b.url, icon: '\u{2733}' })
    }
    for (const h of recent) {
      if (seen.has(h.url) || items.length >= 8) break
      seen.add(h.url)
      items.push({ title: h.title, url: h.url, icon: '\u{23F1}' })
    }
    setShortcuts(items)
  }

  function handleSearch(q: string) {
    if (!q) return
    navigate(`/search?q=${encodeURIComponent(q)}`)
  }

  function openUrl(url: string) {
    navigate(`/browser?url=${encodeURIComponent(url)}`)
  }

  return (
    <div className="screen">
      <div id="home-center">
        <h1 id="home-logo">Localnet</h1>
        <p id="home-sub">your offline internet</p>
        <SearchBar
          id="home-search"
          value={query}
          onChange={setQuery}
          onSubmit={handleSearch}
        />
        <div id="home-shortcuts">
          {shortcuts.map((s) => (
            <button key={s.url} className="shortcut-chip" onClick={() => openUrl(s.url)}>
              <span>{s.icon}</span> {(s.title || s.url).slice(0, 24)}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

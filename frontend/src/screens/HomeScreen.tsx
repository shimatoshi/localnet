import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SearchBar from '../components/SearchBar'
import { bookmarkStore, historyStore } from '../stores/db'
import { useTheme } from '../hooks/useTheme'

interface Shortcut {
  title: string
  url: string
  icon: string
}

export default function HomeScreen() {
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const [query, setQuery] = useState('')
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([])

  useEffect(() => {
    loadShortcuts()
  }, [])

  async function loadShortcuts() {
    const bookmarks = await bookmarkStore.list()
    const history = await historyStore.list(10)
    
    const items: Shortcut[] = []
    const seen = new Set<string>()

    // ブックマークから優先
    for (const b of bookmarks) {
      if (seen.size >= 8) break
      if (!seen.has(b.url)) {
        items.push({ title: b.title, url: b.url, icon: '⭐' })
        seen.add(b.url)
      }
    }

    // 履歴から補充
    for (const h of history) {
      if (seen.size >= 8) break
      if (!seen.has(h.url)) {
        items.push({ title: h.title, url: h.url, icon: '🕒' })
        seen.add(h.url)
      }
    }

    setShortcuts(items)
  }

  function handleSearch(q: string) {
    if (!q) return
    if (q.startsWith('http://') || q.startsWith('https://') || q.includes('.')) {
      let url = q
      if (!q.startsWith('http')) url = 'http://' + q
      navigate(`/browser?url=${encodeURIComponent(url)}`)
    } else {
      navigate(`/search?q=${encodeURIComponent(q)}`)
    }
  }

  function openUrl(url: string) {
    navigate(`/browser?url=${encodeURIComponent(url)}`)
  }

  async function handleSuperReload() {
    try {
      if ('serviceWorker' in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations()
        await Promise.all(regs.map(r => r.unregister()))
      }
      const keys = await caches.keys()
      await Promise.all(keys.map(k => caches.delete(k)))
    } catch { /* ignore */ }
    window.location.href = '/?_=' + Date.now()
  }

  return (
    <div className="screen">
      <button className="floating-btn theme-toggle" onClick={toggleTheme} title="テーマ切り替え">
        {theme === 'light' ? '🌙' : '☀️'}
      </button>
      <button className="floating-btn super-reload" title="スーパーリロード" onClick={handleSuperReload}>
        &#8635;
      </button>

      <div id="home-center">
        <h1 id="home-logo">shimanet</h1>
        
        <div id="home-search-wrap">
          <SearchBar
            id="home-search"
            value={query}
            onChange={setQuery}
            onSubmit={handleSearch}
            placeholder="ウェブを検索、またはURLを入力"
          />
        </div>

        <div id="home-shortcuts">
          {shortcuts.map((s) => (
            <div key={s.url} className="shortcut-chip" onClick={() => openUrl(s.url)}>
              <span className="shortcut-icon">{s.icon}</span>
              <span className="shortcut-text">{(s.title || s.url)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

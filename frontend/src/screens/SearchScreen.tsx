import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import SearchBar from '../components/SearchBar'
import { useOnline } from '../hooks/useOnline'
import { apiSearch, type SearchResult } from '../api/client'
import { catalogStore } from '../stores/db'

export default function SearchScreen() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const online = useOnline()
  const q = params.get('q') || ''
  const [query, setQuery] = useState(q)
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setQuery(q)
    if (q) runSearch(q)
  }, [q])

  async function runSearch(query: string) {
    setLoading(true)
    try {
      let data: SearchResult[]
      if (online) {
        data = await apiSearch(query, 50)
      } else {
        data = await catalogStore.search(query, 50)
      }
      setResults(data)
    } catch {
      // サーバーエラー時フォールバック
      try {
        const data = await catalogStore.search(query, 50)
        setResults(data)
      } catch {
        setResults([])
      }
    } finally {
      setLoading(false)
    }
  }

  function handleSearch(newQ: string) {
    if (!newQ) return
    navigate(`/search?q=${encodeURIComponent(newQ)}`)
  }

  function openUrl(url: string) {
    navigate(`/browser?url=${encodeURIComponent(url)}`)
  }

  return (
    <div className="screen">
      <div id="results-header">
        <span id="results-logo" onClick={() => navigate('/')}>Localnet</span>
        <div id="results-search-wrap">
          <SearchBar
            id="results-search"
            value={query}
            onChange={setQuery}
            onSubmit={handleSearch}
          />
        </div>
      </div>
      <div id="results-web">
        {loading ? (
          <p className="muted" style={{ padding: 20 }}>検索中...</p>
        ) : results.length === 0 ? (
          <p className="muted" style={{ padding: 20 }}>結果なし</p>
        ) : (
          results.map((r, i) => (
            <div key={i} className="result-item" onClick={() => openUrl(r.url)}>
              <div className="result-site">{r.domain}</div>
              <div className="result-title">{r.title || '(無題)'}</div>
              <div className="result-snippet">{r.url}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

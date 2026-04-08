import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import SearchHeader from '../components/SearchHeader'
import LoadingSpinner from '../components/LoadingSpinner'
import EmptyState from '../components/EmptyState'
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
  }, [q, online])

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

  const tabs = [
    { label: 'すべて', active: true, path: '' },
    { label: '画像', active: false, path: `/image-search?q=${encodeURIComponent(q)}` },
  ]

  return (
    <div className="screen">
      <SearchHeader
        query={query}
        onQueryChange={setQuery}
        onSearch={handleSearch}
        tabs={tabs}
      />

      <div id="results-web">
        {loading ? (
          <LoadingSpinner message="検索中..." />
        ) : results.length === 0 ? (
          <EmptyState message="結果が見つかりませんでした" />
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

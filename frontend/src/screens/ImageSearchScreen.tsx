import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import SearchHeader from '../components/SearchHeader'
import LoadingSpinner from '../components/LoadingSpinner'
import EmptyState from '../components/EmptyState'
import ImageLightbox from '../components/ImageLightbox'
import { apiSearchImages, type ImageResult } from '../api/client'

export default function ImageSearchScreen() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const q = params.get('q') || ''
  const [query, setQuery] = useState(q)
  const [results, setResults] = useState<ImageResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<ImageResult | null>(null)
  const [showCount, setShowCount] = useState(24)

  useEffect(() => {
    setQuery(q)
    if (q) runSearch(q)
  }, [q])

  async function runSearch(query: string) {
    setLoading(true)
    try {
      const data = await apiSearchImages(query, 200)
      setResults(data)
      setShowCount(24)
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  function handleSearch(newQ: string) {
    if (!newQ) return
    navigate(`/image-search?q=${encodeURIComponent(newQ)}`)
  }

  function openPage(url: string) {
    navigate(`/browser?url=${encodeURIComponent(url)}`)
  }

  const tabs = [
    { label: 'すべて', active: false, path: `/search?q=${encodeURIComponent(q)}` },
    { label: '画像', active: true, path: '' },
  ]

  return (
    <div className="screen">
      <SearchHeader
        query={query}
        onQueryChange={setQuery}
        onSearch={handleSearch}
        tabs={tabs}
        placeholder="画像を検索..."
      />

      {loading ? (
        <LoadingSpinner message="検索中..." />
      ) : results.length === 0 && q ? (
        <EmptyState message="画像が見つかりませんでした" />
      ) : (
        <div className="image-grid">
          {results.slice(0, showCount).map((img, i) => (
            <div key={i} onClick={() => setSelected(img)} className="image-card">
              <img
                src={img.src}
                alt={img.alt}
                loading="lazy"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            </div>
          ))}
          {showCount < results.length && (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: 24 }}>
              <button
                onClick={() => setShowCount(c => c + 24)}
                className="btn-secondary"
              >
                もっと見る ({results.length - showCount}件)
              </button>
            </div>
          )}
        </div>
      )}

      {selected && (
        <ImageLightbox
          image={selected}
          onClose={() => setSelected(null)}
          onOpenPage={openPage}
        />
      )}
    </div>
  )
}

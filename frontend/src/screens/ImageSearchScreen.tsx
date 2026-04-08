import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import SearchBar from '../components/SearchBar'
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

  return (
    <div className="screen">
      <div id="results-header">
        <span id="results-logo" onClick={() => navigate('/')}>shimanet</span>
        <div id="results-search-wrap">
          <SearchBar
            id="results-search"
            value={query}
            onChange={setQuery}
            onSubmit={handleSearch}
            placeholder="画像を検索..."
          />
        </div>
      </div>

      <div id="results-tabs">
        <button 
          className="results-tab" 
          onClick={() => navigate(`/search?q=${encodeURIComponent(q)}`)}
        >
          すべて
        </button>
        <button className="results-tab active">画像</button>
      </div>

      {loading ? (
        <div style={{ padding: '40px 0', textAlign: 'center' }}>
          <div className="loading-spinner"></div>
          <p className="muted" style={{ marginTop: 16 }}>検索中...</p>
        </div>
      ) : results.length === 0 && q ? (
        <p className="muted" style={{ padding: 20 }}>画像が見つかりませんでした</p>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
          gap: 4,
          padding: '12px',
          paddingBottom: 'var(--nav-offset)',
        }}>
          {results.slice(0, showCount).map((img, i) => (
            <div
              key={i}
              onClick={() => setSelected(img)}
              style={{
                aspectRatio: '1',
                overflow: 'hidden',
                background: 'var(--surface2)',
                cursor: 'pointer',
                borderRadius: 12,
                transition: 'transform 0.2s',
              }}
              className="image-card"
            >
              <img
                src={img.src}
                alt={img.alt}
                loading="lazy"
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            </div>
          ))}
          {showCount < results.length && (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: 24 }}>
              <button
                onClick={() => setShowCount(c => c + 24)}
                className="btn-action"
                style={{ background: 'var(--surface2)', color: 'var(--text)' }}
              >
                もっと見る ({results.length - showCount}件)
              </button>
            </div>
          )}
        </div>
      )}

      {selected && (
        <div
          onClick={() => setSelected(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.9)',
            backdropFilter: 'blur(10px)',
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', zIndex: 2000, padding: 24,
          }}
        >
          <img
            src={selected.src}
            alt={selected.alt}
            style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain', borderRadius: 16, boxShadow: '0 20px 50px rgba(0,0,0,0.5)' }}
            onClick={(e) => e.stopPropagation()}
          />
          <div style={{
            marginTop: 20, color: '#fff', textAlign: 'center',
            maxWidth: '600px',
          }}>
            {selected.alt && <div style={{ marginBottom: 8, fontWeight: 600, fontSize: '1.1em' }}>{selected.alt}</div>}
            <div style={{ color: '#ccc', fontSize: 13, marginBottom: 16 }}>{selected.page_title || selected.domain}</div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button
                onClick={(e) => { e.stopPropagation(); setSelected(null); openPage(selected.page_url) }}
                className="btn-action"
              >
                ページを開く
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setSelected(null) }}
                className="btn-action"
                style={{ background: 'rgba(255,255,255,0.1)' }}
              >
                閉じる
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

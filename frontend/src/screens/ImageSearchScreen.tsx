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

  useEffect(() => {
    setQuery(q)
    if (q) runSearch(q)
  }, [q])

  async function runSearch(query: string) {
    setLoading(true)
    try {
      const data = await apiSearchImages(query, 100)
      setResults(data)
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

      <div style={{ padding: '8px 12px' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <button
            onClick={() => navigate(`/search?q=${encodeURIComponent(q)}`)}
            style={{
              padding: '6px 14px', borderRadius: 20, border: '1px solid var(--surface2)',
              background: 'var(--surface)', color: 'var(--text2)', fontSize: 13, cursor: 'pointer',
            }}
          >
            Web
          </button>
          <button
            style={{
              padding: '6px 14px', borderRadius: 20, border: '1px solid var(--accent)',
              background: 'var(--accent)', color: '#fff', fontSize: 13, cursor: 'pointer',
            }}
          >
            画像
          </button>
        </div>
      </div>

      {loading ? (
        <p className="muted" style={{ padding: 20 }}>検索中...</p>
      ) : results.length === 0 && q ? (
        <p className="muted" style={{ padding: 20 }}>画像が見つかりません</p>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 2,
          padding: '0 2px',
          paddingBottom: 'var(--nav-offset)',
        }}>
          {results.map((img, i) => (
            <div
              key={i}
              onClick={() => setSelected(img)}
              style={{
                aspectRatio: '1',
                overflow: 'hidden',
                background: 'var(--surface)',
                cursor: 'pointer',
              }}
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
        </div>
      )}

      {selected && (
        <div
          onClick={() => setSelected(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', zIndex: 1000, padding: 16,
          }}
        >
          <img
            src={selected.src}
            alt={selected.alt}
            style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: 8 }}
            onClick={(e) => e.stopPropagation()}
          />
          <div style={{
            marginTop: 12, color: '#fff', textAlign: 'center', fontSize: 14,
            maxWidth: '100%', wordBreak: 'break-word',
          }}>
            {selected.alt && <div style={{ marginBottom: 4 }}>{selected.alt}</div>}
            <div style={{ color: '#aaa', fontSize: 12 }}>{selected.page_title || selected.domain}</div>
            <button
              onClick={(e) => { e.stopPropagation(); setSelected(null); openPage(selected.page_url) }}
              style={{
                marginTop: 8, padding: '8px 20px', borderRadius: 20,
                background: 'var(--accent)', color: '#fff', border: 'none',
                fontSize: 13, cursor: 'pointer',
              }}
            >
              ページを開く
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

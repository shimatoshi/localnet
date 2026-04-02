import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import { bookmarkStore, type BookmarkEntry } from '../stores/db'

export default function BookmarksScreen() {
  const navigate = useNavigate()
  const [items, setItems] = useState<BookmarkEntry[]>([])

  useEffect(() => { load() }, [])

  async function load() {
    setItems(await bookmarkStore.list())
  }

  return (
    <div className="screen">
      <SubHeader title="ブックマーク" />
      <div id="bookmarks-list" style={{ padding: '8px 16px' }}>
        {items.length === 0 ? (
          <p className="muted" style={{ padding: '40px 16px', textAlign: 'center' }}>ブックマークなし</p>
        ) : (
          items.map((b) => (
            <div
              key={b.url}
              className="bookmark-item"
              onClick={() => navigate(`/browser?url=${encodeURIComponent(b.url)}`)}
            >
              <div className="bookmark-title">{b.title || b.url}</div>
              <div className="bookmark-url">{b.url}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

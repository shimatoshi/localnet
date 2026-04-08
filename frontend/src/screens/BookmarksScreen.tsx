import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import ListItem from '../components/ListItem'
import EmptyState from '../components/EmptyState'
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
          <EmptyState message="ブックマークなし" />
        ) : (
          items.map((b) => (
            <ListItem
              key={b.url}
              title={b.title || b.url}
              url={b.url}
              className="bookmark-item"
              onClick={() => navigate(`/browser?url=${encodeURIComponent(b.url)}`)}
            />
          ))
        )}
      </div>
    </div>
  )
}

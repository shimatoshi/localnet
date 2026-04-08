import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import ListItem from '../components/ListItem'
import EmptyState from '../components/EmptyState'
import { historyStore, type HistoryEntry } from '../stores/db'

export default function HistoryScreen() {
  const navigate = useNavigate()
  const [items, setItems] = useState<HistoryEntry[]>([])

  useEffect(() => { load() }, [])

  async function load() {
    setItems(await historyStore.list(200))
  }

  async function handleClear() {
    if (!confirm('履歴を消去しますか？')) return
    await historyStore.clear()
    setItems([])
  }

  return (
    <div className="screen">
      <SubHeader title="履歴" action={{ label: '消去', onClick: handleClear }} />
      <div id="history-list" style={{ padding: '8px 16px' }}>
        {items.length === 0 ? (
          <EmptyState message="履歴なし" />
        ) : (
          items.map((h) => (
            <ListItem
              key={h.id}
              title={h.title || h.url}
              url={h.url}
              subtitle={`${new Date(h.timestamp).toLocaleDateString()} ${new Date(h.timestamp).toLocaleTimeString()}`}
              className="history-item"
              onClick={() => navigate(`/browser?url=${encodeURIComponent(h.url)}`)}
            />
          ))
        )}
      </div>
    </div>
  )
}

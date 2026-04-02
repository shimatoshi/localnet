import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
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
          <p className="muted" style={{ padding: '40px 16px', textAlign: 'center' }}>履歴なし</p>
        ) : (
          items.map((h) => (
            <div
              key={h.id}
              className="history-item"
              onClick={() => navigate(`/browser?url=${encodeURIComponent(h.url)}`)}
            >
              <div className="history-title">{h.title || h.url}</div>
              <div className="history-url">{h.url}</div>
              <div className="history-time">
                {new Date(h.timestamp).toLocaleDateString()} {new Date(h.timestamp).toLocaleTimeString()}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

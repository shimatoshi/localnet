import { useState, useRef, useEffect, useCallback } from 'react'
import { historyStore, type HistoryEntry } from '../stores/db'

interface Props {
  id: string
  value: string
  onChange: (v: string) => void
  onSubmit: (q: string) => void
  placeholder?: string
}

export default function SearchBar({ id, value, onChange, onSubmit, placeholder = '検索' }: Props) {
  const [suggestions, setSuggestions] = useState<HistoryEntry[]>([])
  const [showDropdown, setShowDropdown] = useState<boolean>(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const wrapRef = useRef<HTMLDivElement>(null)

  const handleInput = useCallback((q: string) => {
    onChange(q)
    clearTimeout(timerRef.current)
    if (q.trim().length < 2) { setShowDropdown(false); return }
    timerRef.current = setTimeout(async () => {
      const items = await historyStore.searchTitles(q.trim(), 5)
      setSuggestions(items)
      setShowDropdown(items.length > 0)
    }, 200)
  }, [onChange])

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { setShowDropdown(false); onSubmit(value.trim()) }
  }

  useEffect(() => () => clearTimeout(timerRef.current), [])

  return (
    <div ref={wrapRef} style={{ width: '100%' }}>
      <input
        type="search"
        id={id}
        className="search-input"
        value={value}
        onChange={(e) => handleInput(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
        onFocus={() => { if (value.trim().length >= 2) handleInput(value) }}
        placeholder={placeholder}
        autoComplete="off"
      />
      {showDropdown && (
        <div className="suggest-dropdown">
          {suggestions.map((h) => (
            <div
              key={h.id}
              className="suggest-item"
              onMouseDown={() => { setShowDropdown(false); onSubmit(h.title || h.url) }}
            >
              <span className="suggest-icon">{'\u{23F1}'}</span>
              <div className="suggest-text">
                <span className="suggest-title">{h.title || h.url}</span>
                <span className="suggest-url">{h.url}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

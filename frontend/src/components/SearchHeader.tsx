import { useNavigate } from 'react-router-dom'
import SearchBar from './SearchBar'

interface Tab {
  label: string
  active: boolean
  path: string
}

interface Props {
  query: string
  onQueryChange: (q: string) => void
  onSearch: (q: string) => void
  tabs: Tab[]
  placeholder?: string
}

export default function SearchHeader({ query, onQueryChange, onSearch, tabs, placeholder }: Props) {
  const navigate = useNavigate()

  return (
    <>
      <div id="results-header">
        <span id="results-logo" onClick={() => navigate('/')}>shimanet</span>
        <div id="results-search-wrap">
          <SearchBar
            id="results-search"
            value={query}
            onChange={onQueryChange}
            onSubmit={onSearch}
            placeholder={placeholder}
          />
        </div>
      </div>

      <div id="results-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.label}
            className={`results-tab${tab.active ? ' active' : ''}`}
            onClick={() => !tab.active && navigate(tab.path)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </>
  )
}

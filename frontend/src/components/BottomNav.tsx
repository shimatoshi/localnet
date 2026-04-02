import { useLocation, useNavigate } from 'react-router-dom'

const items = [
  { key: 'search', icon: '\u{1F50D}', label: '検索', path: '/' },
  { key: 'data', icon: '\u{1F4E6}', label: 'データ', path: '/datasets' },
  { key: 'crawl', icon: '\u{1F310}', label: 'クロール', path: '/crawl' },
  { key: 'history', icon: '\u{23F1}', label: '履歴', path: '/history' },
  { key: 'bookmarks', icon: '\u{2733}', label: 'ブクマ', path: '/bookmarks' },
]

export default function BottomNav() {
  const location = useLocation()
  const navigate = useNavigate()

  const activeKey = (() => {
    switch (location.pathname) {
      case '/': case '/search': return 'search'
      case '/datasets': return 'data'
      case '/crawl': return 'crawl'
      case '/history': return 'history'
      case '/bookmarks': return 'bookmarks'
      default: return ''
    }
  })()

  return (
    <nav id="main-nav">
      {items.map((item) => (
        <button
          key={item.key}
          className={activeKey === item.key ? 'active' : ''}
          onClick={() => navigate(item.path)}
        >
          <span>{item.icon}</span>
          {item.label}
        </button>
      ))}
    </nav>
  )
}

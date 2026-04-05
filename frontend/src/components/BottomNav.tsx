import { useLocation, useNavigate } from 'react-router-dom'

const items = [
  { key: 'search', icon: '\u{1F50D}', label: '検索', path: '/' },
  { key: 'data', icon: '\u{1F4E6}', label: 'データ', path: '/datasets' },
  { key: 'crawl', icon: '\u{1F310}', label: 'クロール', path: '/crawl' },
  { key: 'manage', icon: '\u{1F6E0}', label: '管理', path: '/manage' },
  { key: 'history', icon: '\u{23F1}', label: '履歴', path: '/history' },
]

export default function BottomNav() {
  const location = useLocation()
  const navigate = useNavigate()

  const activeKey = (() => {
    switch (location.pathname) {
      case '/': case '/search': return 'search'
      case '/datasets': return 'data'
      case '/crawl': return 'crawl'
      case '/manage': return 'manage'
      case '/history': return 'history'
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

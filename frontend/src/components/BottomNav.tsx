import { useLocation, useNavigate } from 'react-router-dom'

const items = [
  { 
    key: 'search', 
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
    ), 
    label: '検索', 
    path: '/' 
  },
  { 
    key: 'data', 
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 8V21H3V8"></path>
        <path d="M1 3H23V8H1V3Z"></path>
        <path d="M10 12H14"></path>
      </svg>
    ), 
    label: 'データ', 
    path: '/datasets' 
  },
  { 
    key: 'crawl', 
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="2" y1="12" x2="22" y2="12"></line>
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
      </svg>
    ), 
    label: 'クロール', 
    path: '/crawl' 
  },
  { 
    key: 'manage', 
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
      </svg>
    ), 
    label: '管理', 
    path: '/manage' 
  },
  { 
    key: 'history', 
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <polyline points="12 6 12 12 16 14"></polyline>
      </svg>
    ), 
    label: '履歴', 
    path: '/history' 
  },
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
          className={`${activeKey === item.key ? 'active' : ''} nav-item-${item.key}`}
          onClick={() => navigate(item.path)}
        >
          <span className="nav-icon">{item.icon}</span>
          {item.label}
        </button>
      ))}
    </nav>
  )
}

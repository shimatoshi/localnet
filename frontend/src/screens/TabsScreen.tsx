import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import { useTabs } from '../hooks/useTabs'

export default function TabsScreen() {
  const navigate = useNavigate()
  const { tabs, activeIndex, addTab, closeTab, switchTab } = useTabs()

  function handleAdd() {
    addTab()
    navigate('/')
  }

  function handleSelect(index: number) {
    switchTab(index)
    const tab = tabs[index]
    if (tab.url) {
      navigate(`/browser?url=${encodeURIComponent(tab.url)}`)
    } else {
      navigate('/')
    }
  }

  return (
    <div className="screen">
      <SubHeader title="タブ" action={{ label: '+ 新規', onClick: handleAdd }} />
      <div id="tabs-list" style={{ padding: 8 }}>
        {tabs.length === 0 ? (
          <p className="muted" style={{ padding: '40px 16px', textAlign: 'center' }}>タブなし</p>
        ) : (
          tabs.map((tab, i) => (
            <div
              key={tab.id}
              className={`tab-card${i === activeIndex ? ' active-tab' : ''}`}
              onClick={() => handleSelect(i)}
            >
              <div className="tab-title">{tab.title || '新しいタブ'}</div>
              <button
                className="tab-close"
                onClick={(e) => { e.stopPropagation(); closeTab(i) }}
              >
                &times;
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

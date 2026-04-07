import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles/global.css'

// Service Worker — サーバーのdev_modeに従う
fetch('/api/version').then(r => r.json()).then(data => {
  if (data.dev_mode) {
    // dev_mode: SW登録解除+キャッシュ全削除
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistrations().then(regs =>
        regs.forEach(r => r.unregister())
      )
    }
    if ('caches' in window) {
      caches.keys().then(keys => keys.forEach(k => caches.delete(k)))
    }
    console.log('[dev] Service Worker disabled, caches cleared')
  } else {
    // 本番: SW登録
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {})
    }
    if (navigator.storage?.persist) {
      navigator.storage.persist().then((granted) => {
        if (!granted) {
          console.warn('Storage persistence not granted — cached data may be evicted')
        }
      })
    }
  }
}).catch(() => {
  // API到達不可（オフライン等）→ SW登録を試みる
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)

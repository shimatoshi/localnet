import { useState, useEffect } from 'react'
import SubHeader from '../components/SubHeader'
import { useOnline } from '../hooks/useOnline'
import { apiGetSites, apiGetCatalog, type SiteInfo } from '../api/client'
import { catalogStore, type CatalogData } from '../stores/db'

/** HTML文字列からCSS/JS/画像のURLを抽出し、/api/cache/ パスで返す */
function extractSubResources(html: string, domain: string): string[] {
  const cachePrefix = `/api/cache/${encodeURIComponent(domain)}/`
  const patterns = [
    /<link[^>]+href=["']([^"']+)["'][^>]*>/gi,
    /<script[^>]+src=["']([^"']+)["'][^>]*>/gi,
    /<img[^>]+src=["']([^"']+)["'][^>]*>/gi,
  ]
  const urls: string[] = []
  for (const re of patterns) {
    let m: RegExpExecArray | null
    while ((m = re.exec(html)) !== null) {
      const ref = m[1]
      if (ref.startsWith('data:')) continue
      if (ref.startsWith(cachePrefix)) {
        urls.push(ref)
      } else if (ref.startsWith('/') && !ref.startsWith('//')) {
        urls.push(`${cachePrefix}${ref.slice(1)}`)
      }
    }
  }
  return urls
}

export default function DatasetsScreen() {
  const online = useOnline()
  const [serverSites, setServerSites] = useState<SiteInfo[]>([])
  const [localCatalogs, setLocalCatalogs] = useState<CatalogData[]>([])
  const [downloading, setDownloading] = useState<Record<string, string>>({})

  useEffect(() => {
    if (online) loadServer()
    loadLocal()
  }, [online])

  async function loadServer() {
    try {
      const sites = await apiGetSites()
      setServerSites(sites.filter((s) => s.has_catalog))
    } catch {
      setServerSites([])
    }
  }

  async function loadLocal() {
    try {
      setLocalCatalogs(await catalogStore.list())
    } catch {
      setLocalCatalogs([])
    }
  }

  async function downloadDataset(domain: string) {
    setDownloading((prev) => ({ ...prev, [domain]: 'カタログ取得中...' }))
    try {
      // キャッシュクリア
      try {
        const cacheNames = await caches.keys()
        for (const name of cacheNames) {
          const cache = await caches.open(name)
          const keys = await cache.keys()
          for (const req of keys) {
            if (req.url.includes(`/api/cache/${domain}/`) || req.url.includes(`/api/catalog/${domain}`)) {
              await cache.delete(req)
            }
          }
        }
      } catch { /* ignore */ }

      const entries = await apiGetCatalog(domain)
      await catalogStore.save(domain, entries)

      // 全ページをfetchしてSWキャッシュに載せる + サブリソースも取得
      let done = 0
      const subResourceUrls = new Set<string>()
      const queue = [...entries]
      const concurrency = 3
      const domainEnc = encodeURIComponent(domain)
      const cachePrefix = `/api/cache/${domainEnc}/`

      async function worker() {
        while (queue.length > 0) {
          const entry = queue.shift()!
          try {
            const res = await fetch(`${cachePrefix}${entry.path}`)
            if (res.ok) {
              // HTMLからサブリソースURL抽出
              const html = await res.text()
              extractSubResources(html, domain).forEach((u) => subResourceUrls.add(u))
            }
          } catch { /* ignore */ }
          done++
          setDownloading((prev) => ({ ...prev, [domain]: `ページ ${done} / ${entries.length}` }))
        }
      }

      await Promise.all(Array.from({ length: concurrency }, () => worker()))

      // サブリソース（CSS/JS/画像）をプリフェッチ
      if (subResourceUrls.size > 0) {
        setDownloading((prev) => ({ ...prev, [domain]: `リソース 0 / ${subResourceUrls.size}` }))
        let resDone = 0
        const resQueue = [...subResourceUrls]
        async function resWorker() {
          while (resQueue.length > 0) {
            const url = resQueue.shift()!
            try { await fetch(url) } catch { /* ignore */ }
            resDone++
            if (resDone % 10 === 0 || resQueue.length === 0) {
              setDownloading((prev) => ({ ...prev, [domain]: `リソース ${resDone} / ${subResourceUrls.size}` }))
            }
          }
        }
        await Promise.all(Array.from({ length: concurrency }, () => resWorker()))
      }

      setDownloading((prev) => ({ ...prev, [domain]: '完了' }))
      loadLocal()
    } catch {
      setDownloading((prev) => ({ ...prev, [domain]: 'エラー' }))
    }
  }

  async function removeLocal(domain: string) {
    if (!confirm(`${domain} を削除しますか？`)) return
    await catalogStore.remove(domain)
    try {
      const cacheNames = await caches.keys()
      for (const name of cacheNames) {
        const cache = await caches.open(name)
        const keys = await cache.keys()
        for (const req of keys) {
          if (req.url.includes(`/api/cache/${domain}/`)) await cache.delete(req)
        }
      }
    } catch { /* ignore */ }
    loadLocal()
    if (online) loadServer()
  }

  const localDomains = new Set(localCatalogs.map((c) => c.domain))

  return (
    <div className="screen">
      <SubHeader title="Datasets" />

      {!online && <p className="muted" style={{ padding: '8px 16px' }}>オフライン</p>}

      {online && (
        <section style={{ marginTop: 0 }}>
          <h2>サーバー</h2>
          {serverSites.length === 0 ? (
            <p className="muted">データセットなし</p>
          ) : (
            serverSites.map((site) => (
              <div key={site.domain} className="dataset-item">
                <div className="dataset-name">{site.domain}</div>
                <div className="dataset-info">{site.page_count} ページ / {site.file_count} ファイル</div>
                <div className="dataset-actions">
                  {localDomains.has(site.domain) && (
                    <button className="btn-downloaded" disabled>&#10003; DL済み</button>
                  )}
                  <button
                    className="btn-download"
                    disabled={!!downloading[site.domain]}
                    onClick={() => downloadDataset(site.domain)}
                  >
                    {downloading[site.domain] || (localDomains.has(site.domain) ? '更新' : 'ダウンロード')}
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      )}

      <section style={{ marginTop: 12 }}>
        <h2>ダウンロード済み</h2>
        {localCatalogs.length === 0 ? (
          <p className="muted">なし</p>
        ) : (
          localCatalogs.map((cat) => (
            <div key={cat.domain} className="dataset-item">
              <div className="dataset-name">{cat.domain}</div>
              <div className="dataset-info">
                {cat.entries.length} ページ / {new Date(cat.downloadedAt).toLocaleDateString()}
              </div>
              <div className="dataset-actions">
                <button className="btn-delete" onClick={() => removeLocal(cat.domain)}>削除</button>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

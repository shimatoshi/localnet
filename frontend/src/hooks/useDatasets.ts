import { useState, useEffect, useCallback } from 'react'
import { apiGetSites, apiGetCatalog, type SiteInfo } from '../api/client'
import { catalogStore, type CatalogData } from '../stores/db'
import { extractSubResources } from '../utils/htmlTransform'

export function useDatasets(online: boolean) {
  const [serverSites, setServerSites] = useState<SiteInfo[]>([])
  const [localCatalogs, setLocalCatalogs] = useState<CatalogData[]>([])
  const [downloading, setDownloading] = useState<Record<string, string>>({})

  const loadLocal = useCallback(async () => {
    try { setLocalCatalogs(await catalogStore.list()) } catch { setLocalCatalogs([]) }
  }, [])

  const loadServer = useCallback(async () => {
    try {
      const sites = await apiGetSites()
      setServerSites(sites.filter((s) => s.has_catalog))
    } catch { setServerSites([]) }
  }, [])

  useEffect(() => {
    if (online) loadServer()
    loadLocal()
  }, [online, loadServer, loadLocal])

  async function downloadDataset(domain: string) {
    setDownloading((prev) => ({ ...prev, [domain]: 'カタログ取得中...' }))
    try {
      // 既存キャッシュクリア
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

      // ページ取得 + サブリソースURL収集
      let done = 0
      const subResourceUrls = new Set<string>()
      const queue = [...entries]
      const concurrency = 3
      const cachePrefix = `/api/cache/${encodeURIComponent(domain)}/`

      async function worker() {
        while (queue.length > 0) {
          const entry = queue.shift()!
          try {
            const res = await fetch(`${cachePrefix}${entry.path}`)
            if (res.ok) {
              const html = await res.text()
              extractSubResources(html, domain).forEach((u) => subResourceUrls.add(u))
            }
          } catch { /* ignore */ }
          done++
          setDownloading((prev) => ({ ...prev, [domain]: `ページ ${done} / ${entries.length}` }))
        }
      }
      await Promise.all(Array.from({ length: concurrency }, () => worker()))

      // サブリソースプリフェッチ
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

  return { serverSites, localCatalogs, downloading, downloadDataset, removeLocal }
}

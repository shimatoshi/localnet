/** IndexedDB — 履歴・ブックマーク・カタログ */

const DB_NAME = 'localnet'
const DB_VERSION = 5
const STORE_HISTORY = 'history'
const STORE_BOOKMARKS = 'bookmarks'
const STORE_CATALOGS = 'catalogs'

let _db: IDBDatabase | null = null

function openDB(): Promise<IDBDatabase> {
  if (_db) return Promise.resolve(_db)
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (e) => {
      const db = (e.target as IDBOpenDBRequest).result
      for (const name of ['datasets_meta', 'datasets_data', 'search_index']) {
        if (db.objectStoreNames.contains(name)) db.deleteObjectStore(name)
      }
      if (!db.objectStoreNames.contains(STORE_HISTORY)) {
        const hs = db.createObjectStore(STORE_HISTORY, { keyPath: 'id', autoIncrement: true })
        hs.createIndex('timestamp', 'timestamp')
        hs.createIndex('url', 'url')
      }
      if (!db.objectStoreNames.contains(STORE_BOOKMARKS)) {
        db.createObjectStore(STORE_BOOKMARKS, { keyPath: 'url' })
      }
      if (!db.objectStoreNames.contains(STORE_CATALOGS)) {
        db.createObjectStore(STORE_CATALOGS, { keyPath: 'domain' })
      }
    }
    req.onsuccess = (e) => {
      _db = (e.target as IDBOpenDBRequest).result
      resolve(_db)
    }
    req.onerror = () => reject(req.error)
  })
}

// === Types ===

export interface HistoryEntry {
  id?: number
  url: string
  title: string
  timestamp: number
}

export interface BookmarkEntry {
  url: string
  title: string
  created: number
}

export interface CatalogData {
  domain: string
  entries: CatalogEntry[]
  downloadedAt: number
}

export interface CatalogEntry {
  url: string
  title: string
  path: string
}

// === 履歴 ===

export const historyStore = {
  async add(entry: { url: string; title: string }) {
    const db = await openDB()
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readwrite')
      tx.objectStore(STORE_HISTORY).add({
        url: entry.url,
        title: entry.title || '',
        timestamp: Date.now(),
      })
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  },

  async list(limit = 100): Promise<HistoryEntry[]> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readonly')
      const idx = tx.objectStore(STORE_HISTORY).index('timestamp')
      const req = idx.openCursor(null, 'prev')
      const results: HistoryEntry[] = []
      req.onsuccess = (e) => {
        const cursor = (e.target as IDBRequest<IDBCursorWithValue | null>).result
        if (cursor && results.length < limit) {
          results.push(cursor.value)
          cursor.continue()
        } else {
          resolve(results)
        }
      }
      req.onerror = () => reject(req.error)
    })
  },

  async clear() {
    const db = await openDB()
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readwrite')
      tx.objectStore(STORE_HISTORY).clear()
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  },

  async searchTitles(query: string, limit = 8): Promise<HistoryEntry[]> {
    const items = await this.list(500)
    const q = query.toLowerCase()
    const seen = new Set<string>()
    return items.filter((h) => {
      if (seen.has(h.url)) return false
      seen.add(h.url)
      return h.title.toLowerCase().includes(q) || h.url.toLowerCase().includes(q)
    }).slice(0, limit)
  },
}

// === ブックマーク ===

export const bookmarkStore = {
  async add(entry: { url: string; title: string }) {
    const db = await openDB()
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readwrite')
      tx.objectStore(STORE_BOOKMARKS).put({
        url: entry.url,
        title: entry.title || '',
        created: Date.now(),
      })
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  },

  async remove(url: string) {
    const db = await openDB()
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readwrite')
      tx.objectStore(STORE_BOOKMARKS).delete(url)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  },

  async has(url: string): Promise<boolean> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readonly')
      const req = tx.objectStore(STORE_BOOKMARKS).get(url)
      req.onsuccess = () => resolve(!!req.result)
      req.onerror = () => reject(req.error)
    })
  },

  async list(): Promise<BookmarkEntry[]> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readonly')
      const req = tx.objectStore(STORE_BOOKMARKS).getAll()
      req.onsuccess = () => resolve(req.result || [])
      req.onerror = () => reject(req.error)
    })
  },
}

// === カタログ ===

export const catalogStore = {
  async save(domain: string, entries: CatalogEntry[]) {
    const db = await openDB()
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readwrite')
      tx.objectStore(STORE_CATALOGS).put({ domain, entries, downloadedAt: Date.now() })
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  },

  async get(domain: string): Promise<CatalogData | null> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readonly')
      const req = tx.objectStore(STORE_CATALOGS).get(domain)
      req.onsuccess = () => resolve(req.result || null)
      req.onerror = () => reject(req.error)
    })
  },

  async list(): Promise<CatalogData[]> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readonly')
      const req = tx.objectStore(STORE_CATALOGS).getAll()
      req.onsuccess = () => resolve(req.result || [])
      req.onerror = () => reject(req.error)
    })
  },

  async remove(domain: string) {
    const db = await openDB()
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readwrite')
      tx.objectStore(STORE_CATALOGS).delete(domain)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  },

  async search(query: string, limit = 50) {
    const all = await this.list()
    const q = query.toLowerCase()
    const results: (CatalogEntry & { domain: string })[] = []
    for (const cat of all) {
      for (const entry of cat.entries) {
        if ((entry.title || '').toLowerCase().includes(q) || (entry.path || '').toLowerCase().includes(q)) {
          results.push({ ...entry, domain: cat.domain })
          if (results.length >= limit) return results
        }
      }
    }
    return results
  },
}

// IndexedDB ラッパー — データセット + 履歴 + ブックマーク

const DB_NAME = 'localnet';
const DB_VERSION = 2;
const STORE_META = 'datasets_meta';
const STORE_DATA = 'datasets_data';
const STORE_HISTORY = 'history';
const STORE_BOOKMARKS = 'bookmarks';

let _db = null;

function openDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_META)) {
        db.createObjectStore(STORE_META, { keyPath: 'name' });
      }
      if (!db.objectStoreNames.contains(STORE_DATA)) {
        db.createObjectStore(STORE_DATA, { keyPath: 'name' });
      }
      if (!db.objectStoreNames.contains(STORE_HISTORY)) {
        const hs = db.createObjectStore(STORE_HISTORY, { keyPath: 'id', autoIncrement: true });
        hs.createIndex('timestamp', 'timestamp');
        hs.createIndex('url', 'url');
      }
      if (!db.objectStoreNames.contains(STORE_BOOKMARKS)) {
        db.createObjectStore(STORE_BOOKMARKS, { keyPath: 'url' });
      }
    };
    req.onsuccess = (e) => {
      _db = e.target.result;
      resolve(_db);
    };
    req.onerror = () => reject(req.error);
  });
}

// === データセット ===
const dbStore = {
  async save(name, arrayBuffer, meta) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_META, STORE_DATA], 'readwrite');
      tx.objectStore(STORE_META).put({
        name,
        source_url: meta.source_url || '',
        created_at: meta.created_at || '',
        page_count: meta.page_count || 0,
        size_bytes: arrayBuffer.byteLength,
        downloaded_at: new Date().toISOString(),
      });
      tx.objectStore(STORE_DATA).put({ name, data: arrayBuffer });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async load(name) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_DATA, 'readonly');
      const req = tx.objectStore(STORE_DATA).get(name);
      req.onsuccess = () => resolve(req.result ? req.result.data : null);
      req.onerror = () => reject(req.error);
    });
  },
  async listMeta() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_META, 'readonly');
      const req = tx.objectStore(STORE_META).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  },
  async has(name) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_META, 'readonly');
      const req = tx.objectStore(STORE_META).get(name);
      req.onsuccess = () => resolve(!!req.result);
      req.onerror = () => reject(req.error);
    });
  },
  async delete(name) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_META, STORE_DATA], 'readwrite');
      tx.objectStore(STORE_META).delete(name);
      tx.objectStore(STORE_DATA).delete(name);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
};

// === 履歴 ===
const historyStore = {
  async add(entry) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readwrite');
      tx.objectStore(STORE_HISTORY).add({
        url: entry.url,
        title: entry.title || '',
        dataset: entry.dataset || '',
        pageId: entry.pageId || 0,
        timestamp: Date.now(),
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async list(limit = 100) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readonly');
      const idx = tx.objectStore(STORE_HISTORY).index('timestamp');
      const req = idx.openCursor(null, 'prev');
      const results = [];
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor && results.length < limit) {
          results.push(cursor.value);
          cursor.continue();
        } else {
          resolve(results);
        }
      };
      req.onerror = () => reject(req.error);
    });
  },
  async clear() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readwrite');
      tx.objectStore(STORE_HISTORY).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async searchTitles(query, limit = 8) {
    const items = await this.list(500);
    const q = query.toLowerCase();
    const seen = new Set();
    return items.filter(h => {
      const key = h.url;
      if (seen.has(key)) return false;
      seen.add(key);
      return h.title.toLowerCase().includes(q) || h.url.toLowerCase().includes(q);
    }).slice(0, limit);
  },
};

// === ブックマーク ===
const bookmarkStore = {
  async add(entry) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readwrite');
      tx.objectStore(STORE_BOOKMARKS).put({
        url: entry.url,
        title: entry.title || '',
        dataset: entry.dataset || '',
        pageId: entry.pageId || 0,
        created: Date.now(),
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async remove(url) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readwrite');
      tx.objectStore(STORE_BOOKMARKS).delete(url);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async has(url) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readonly');
      const req = tx.objectStore(STORE_BOOKMARKS).get(url);
      req.onsuccess = () => resolve(!!req.result);
      req.onerror = () => reject(req.error);
    });
  },
  async list() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_BOOKMARKS, 'readonly');
      const req = tx.objectStore(STORE_BOOKMARKS).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  },
};

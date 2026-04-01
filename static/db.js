// IndexedDB ラッパー — 履歴 + ブックマーク

const DB_NAME = 'localnet';
const DB_VERSION = 5;
const STORE_HISTORY = 'history';
const STORE_BOOKMARKS = 'bookmarks';
const STORE_CATALOGS = 'catalogs';

let _db = null;

function openDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      // 旧ストアを削除
      for (const name of ['datasets_meta', 'datasets_data', 'search_index']) {
        if (db.objectStoreNames.contains(name)) db.deleteObjectStore(name);
      }
      if (!db.objectStoreNames.contains(STORE_HISTORY)) {
        const hs = db.createObjectStore(STORE_HISTORY, { keyPath: 'id', autoIncrement: true });
        hs.createIndex('timestamp', 'timestamp');
        hs.createIndex('url', 'url');
      }
      if (!db.objectStoreNames.contains(STORE_BOOKMARKS)) {
        db.createObjectStore(STORE_BOOKMARKS, { keyPath: 'url' });
      }
      if (!db.objectStoreNames.contains(STORE_CATALOGS)) {
        db.createObjectStore(STORE_CATALOGS, { keyPath: 'domain' });
      }
    };
    req.onsuccess = (e) => {
      _db = e.target.result;
      resolve(_db);
    };
    req.onerror = () => reject(req.error);
  });
}

// === 履歴 ===
const historyStore = {
  async add(entry) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_HISTORY, 'readwrite');
      tx.objectStore(STORE_HISTORY).add({
        url: entry.url,
        title: entry.title || '',
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

// === カタログ ===
const catalogStore = {
  async save(domain, entries) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readwrite');
      tx.objectStore(STORE_CATALOGS).put({ domain, entries, downloadedAt: Date.now() });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async get(domain) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readonly');
      const req = tx.objectStore(STORE_CATALOGS).get(domain);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  },
  async list() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readonly');
      const req = tx.objectStore(STORE_CATALOGS).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  },
  async remove(domain) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_CATALOGS, 'readwrite');
      tx.objectStore(STORE_CATALOGS).delete(domain);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  },
  async search(query, limit = 50) {
    const all = await this.list();
    const q = query.toLowerCase();
    const results = [];
    for (const cat of all) {
      for (const entry of cat.entries) {
        if ((entry.title || '').toLowerCase().includes(q) || (entry.path || '').toLowerCase().includes(q)) {
          results.push({ ...entry, domain: cat.domain });
          if (results.length >= limit) return results;
        }
      }
    }
    return results;
  },
};

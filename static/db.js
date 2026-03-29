// IndexedDB ラッパー — データセット永続保存

const DB_NAME = 'localnet';
const DB_VERSION = 1;
const STORE_META = 'datasets_meta';
const STORE_DATA = 'datasets_data';

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
    };
    req.onsuccess = (e) => {
      _db = e.target.result;
      resolve(_db);
    };
    req.onerror = () => reject(req.error);
  });
}

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
      tx.objectStore(STORE_DATA).put({
        name,
        data: arrayBuffer,
      });
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

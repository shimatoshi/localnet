const CACHE_NAME = 'localnet-v2';
const APP_SHELL = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/db.js',
  '/static/sqldb.js',
  '/static/search.js',
  '/static/datasets.js',
  '/static/viewer.js',
  '/static/crawl.js',
  '/static/manifest.json',
];

const CDN_ASSETS = [
  'https://sql.js.org/dist/sql-wasm.js',
  'https://sql.js.org/dist/sql-wasm.wasm',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // App shell は必須
      const appPromise = cache.addAll(APP_SHELL);
      // CDNアセットは失敗しても続行
      const cdnPromise = Promise.allSettled(
        CDN_ASSETS.map(url => cache.add(url).catch(() => console.warn('CDN cache miss:', url)))
      );
      return Promise.all([appPromise, cdnPromise]);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API: ネットワークファースト
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(JSON.stringify({ error: 'オフラインです' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        });
      })
    );
    return;
  }

  // その他: キャッシュファースト
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        // 成功したレスポンスをキャッシュ
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      });
    })
  );
});

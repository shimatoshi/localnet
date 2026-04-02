const CACHE_NAME = 'localnet-v10';
const APP_SHELL = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/tabs.js',
  '/static/sse.js',
  '/static/browser.js',
  '/static/db.js',
  '/static/search.js',
  '/static/datasets.js',
  '/static/crawl.js',
  '/static/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
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

/**
 * ネットワークfetch — 非2xxもエラー扱い
 * 502/503等はfetch成功だがSWとしてはキャッシュフォールバックすべき
 */
function fetchOrFail(request) {
  return fetch(request).then((response) => {
    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }
    return response;
  });
}

self.addEventListener('fetch', (event) => {
  var url = new URL(event.request.url);

  if (event.request.method !== 'GET') {
    return;
  }

  // /api/cache/* → Cache-First（オフライン閲覧の本体）
  if (url.pathname.startsWith('/api/cache/')) {
    event.respondWith(
      caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        return fetch(event.request).then(function(response) {
          if (response.ok) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
          }
          return response;
        });
      }).catch(function() {
        return new Response('オフライン: このページはダウンロードされていません', { status: 503 });
      })
    );
    return;
  }

  // /api/catalog/* → Network-First + キャッシュフォールバック
  if (url.pathname.startsWith('/api/catalog/')) {
    event.respondWith(
      fetchOrFail(event.request).then(function(response) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
        return response;
      }).catch(function() {
        return caches.match(event.request).then(function(cached) {
          if (cached) return cached;
          return new Response(JSON.stringify({ error: 'オフラインです' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
          });
        });
      })
    );
    return;
  }

  // /api/search → Network-First + キャッシュフォールバック
  if (url.pathname === '/api/search') {
    event.respondWith(
      fetchOrFail(event.request).then(function(response) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
        return response;
      }).catch(function() {
        return caches.match(event.request).then(function(cached) {
          if (cached) return cached;
          return new Response(JSON.stringify([]), {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
          });
        });
      })
    );
    return;
  }

  // /api/* (その他) → ネットワークのみ
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(function() {
        return new Response(JSON.stringify({ error: 'オフラインです' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        });
      })
    );
    return;
  }

  // 静的ファイル + ナビゲーション: Network-First + キャッシュフォールバック
  event.respondWith(
    fetchOrFail(event.request).then(function(response) {
      var clone = response.clone();
      caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
      return response;
    }).catch(function() {
      return caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        // SPA: ナビゲーションならindex.htmlを返す
        if (event.request.mode === 'navigate') {
          return caches.match('/');
        }
        return new Response('オフライン', { status: 503 });
      });
    })
  );
});

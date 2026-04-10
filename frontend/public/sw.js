const CACHE_NAME = 'shimanet-v6';

const APP_SHELL = self.__APP_SHELL || [
  '/',
  '/manifest.json',
  '/icon-192.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      const keys = await cache.keys();
      const stale = keys.filter((req) => {
        const p = new URL(req.url).pathname;
        return p.startsWith('/assets/') || p === '/' || p === '/index.html' || p === '/sw.js';
      });
      await Promise.all(stale.map((req) => cache.delete(req)));
      await Promise.all(APP_SHELL.map(async (url) => {
        try {
          const res = await fetch(url);
          if (res.ok) await cache.put(url, res);
        } catch { /* skip */ }
      }));
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // POST → そのまま通す
  if (event.request.method !== 'GET') return;

  // /api/cache/* → オフライン閲覧用。Network-First + キャッシュ保存
  if (url.pathname.startsWith('/api/cache/')) {
    event.respondWith(
      fetch(event.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return res;
      }).catch(() =>
        caches.match(event.request).then(c =>
          c || new Response('オフライン', { status: 503 })
        )
      )
    );
    return;
  }

  // /api/catalog/* → Network-First + キャッシュ保存
  if (url.pathname.startsWith('/api/catalog/')) {
    event.respondWith(
      fetch(event.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return res;
      }).catch(() =>
        caches.match(event.request).then(c =>
          c || new Response(JSON.stringify({ error: 'オフライン' }), {
            status: 503, headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    return;
  }

  // /api/search → Network-First + キャッシュ保存
  if (url.pathname === '/api/search') {
    event.respondWith(
      fetch(event.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return res;
      }).catch(() =>
        caches.match(event.request).then(c =>
          c || new Response(JSON.stringify([]), {
            status: 503, headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    return;
  }

  // /api/* (sites, jobs, crawl等) → SWは触らない。ブラウザが直接fetch
  if (url.pathname.startsWith('/api/')) return;

  // SPA ナビゲーション → Network-First
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return res;
      }).catch(() =>
        caches.match('/').then(c => c || caches.match('/index.html')).then(c =>
          c || new Response('オフライン', { status: 503 })
        )
      )
    );
    return;
  }

  // 静的ファイル → Network-First
  event.respondWith(
    fetch(event.request).then((res) => {
      if (res.ok) {
        const clone = res.clone();
        caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
      }
      return res;
    }).catch(() =>
      caches.match(event.request).then(c =>
        c || new Response('オフライン', { status: 503 })
      )
    )
  );
});

const CACHE_NAME = 'localnet-v6';
const APP_SHELL = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/db.js',
  '/static/search.js',
  '/static/viewer.js',
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

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  event.respondWith(
    fetch(event.request).then((response) => {
      if (response.ok && event.request.method === 'GET') {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
      }
      return response;
    }).catch(() => {
      return caches.match(event.request).then((cached) => {
        if (cached) return cached;
        if (url.pathname.startsWith('/api/')) {
          return new Response(JSON.stringify({ error: 'オフラインです' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response('オフライン', { status: 503 });
      });
    })
  );
});

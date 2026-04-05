const CACHE_NAME = 'shimanet-v1';

// ビルド時に __APP_SHELL__ がassetリストに置換される
// 開発時はフォールバックで基本ファイルのみ
const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icon-192.png",
  "/sw.js",
  "/assets/index-B8rdIQE2.js",
  "/assets/index-kHDG7MAH.css"
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_SHELL);
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

/**
 * ネットワークfetch — 非2xxレスポンスもエラー扱いにするラッパー
 * 502/503等はfetchとしては「成功」だが、SWとしてはキャッシュフォールバックすべき
 */
function fetchOrFail(request) {
  return fetch(request).then((response) => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response;
  });
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // POST等の書き込み系 → 常にネットワーク（キャッシュ不可）
  if (event.request.method !== 'GET') {
    return;
  }

  // /api/cache/* → オフライン閲覧の本体。Cache-First（キャッシュ優先）
  // DLボタンで事前fetchした結果がここに溜まる
  if (url.pathname.startsWith('/api/cache/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
      }).catch(() => {
        return new Response('オフライン: このページはダウンロードされていません', { status: 503 });
      })
    );
    return;
  }

  // /api/catalog/* → Network-First + キャッシュフォールバック
  if (url.pathname.startsWith('/api/catalog/')) {
    event.respondWith(
      fetchOrFail(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      }).catch(() => {
        return caches.match(event.request).then((cached) => {
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

  // /api/search → Network-First + キャッシュフォールバック（検索結果もキャッシュ）
  if (url.pathname === '/api/search') {
    event.respondWith(
      fetchOrFail(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      }).catch(() => {
        return caches.match(event.request).then((cached) => {
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

  // /api/* (その他: crawl, jobs等) → ネットワークのみ。オフラインで使えない機能
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

  // SPAナビゲーション: /search, /browser 等 → Network-First、失敗時はキャッシュのindex.html
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetchOrFail(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      }).catch(() => {
        return caches.match('/').then((cached) => {
          return cached || caches.match('/index.html');
        }).then((cached) => {
          return cached || new Response('オフライン', { status: 503 });
        });
      })
    );
    return;
  }

  // 静的ファイル (JS/CSS/画像等): Network-First + キャッシュフォールバック
  event.respondWith(
    fetchOrFail(event.request).then((response) => {
      const clone = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
      return response;
    }).catch(() => {
      return caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return new Response('オフライン', { status: 503 });
      });
    })
  );
});

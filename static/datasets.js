// データセット管理

let _downloadAbort = null;

function onDataTabOpen() {
  if (isOnline) {
    hide('data-offline');
    show('server-datasets-section');
    loadServerDatasets();
  } else {
    show('data-offline');
    hide('server-datasets-section');
    $('server-datasets').innerHTML = '<p class="muted">オフライン</p>';
  }
  loadLocalDatasets();
}

async function loadServerDatasets() {
  const el = $('server-datasets');
  try {
    const res = await fetch('/api/sites');
    const sites = await res.json();
    const catalogs = sites.filter(s => s.has_catalog);
    if (catalogs.length === 0) {
      el.innerHTML = '<p class="muted">データセットなし</p>';
      return;
    }
    const localList = await catalogStore.list();
    const localDomains = new Set(localList.map(c => c.domain));
    el.innerHTML = '';
    for (const site of catalogs) {
      const item = document.createElement('div');
      item.className = 'dataset-item';
      const isLocal = localDomains.has(site.domain);
      item.innerHTML = `
        <div class="dataset-name">${escHtml(site.domain)}</div>
        <div class="dataset-info">${site.page_count} ページ / ${site.file_count} ファイル</div>
        <div class="dataset-actions">
          ${isLocal
            ? '<button class="btn-downloaded" disabled>&#10003; DL済み</button>'
            : `<button class="btn-download" data-domain="${escHtml(site.domain)}">ダウンロード</button>`}
        </div>
        <div class="progress-bar-wrap hidden" data-progress="${escHtml(site.domain)}">
          <div class="progress-bar-fill"></div>
        </div>
      `;
      el.appendChild(item);
      if (!isLocal) {
        item.querySelector('.btn-download').addEventListener('click', function() {
          downloadDataset(site.domain, this, item);
        });
      }
    }
  } catch (e) {
    el.innerHTML = '<p class="muted">サーバーに接続できません</p>';
  }
}

async function loadLocalDatasets() {
  const el = $('local-datasets');
  try {
    const catalogs = await catalogStore.list();
    if (catalogs.length === 0) {
      el.innerHTML = '<p class="muted">なし</p>';
      return;
    }
    el.innerHTML = '';
    for (const cat of catalogs) {
      const item = document.createElement('div');
      item.className = 'dataset-item';
      const d = new Date(cat.downloadedAt);
      item.innerHTML = `
        <div class="dataset-name">${escHtml(cat.domain)}</div>
        <div class="dataset-info">${cat.entries.length} ページ / ${d.toLocaleDateString()}</div>
        <div class="dataset-actions">
          <button class="btn-delete" data-domain="${escHtml(cat.domain)}">削除</button>
        </div>
      `;
      el.appendChild(item);
      item.querySelector('.btn-delete').addEventListener('click', async function() {
        if (!confirm(`${cat.domain} を削除しますか？`)) return;
        await catalogStore.remove(cat.domain);
        // SWキャッシュからも削除
        try {
          const cache = await caches.open('localnet-v7');
          const keys = await cache.keys();
          for (const req of keys) {
            if (req.url.includes(`/api/cache/${cat.domain}/`)) {
              await cache.delete(req);
            }
          }
        } catch (e) {}
        loadLocalDatasets();
        if (isOnline) loadServerDatasets();
      });
    }
  } catch (e) {
    el.innerHTML = '<p class="muted">読み込みエラー</p>';
  }
}

async function downloadDataset(domain, btn, item) {
  btn.disabled = true;
  btn.textContent = 'カタログ取得中...';
  const progressWrap = item.querySelector('.progress-bar-wrap');
  const progressFill = item.querySelector('.progress-bar-fill');
  progressWrap.classList.remove('hidden');

  try {
    // 1. カタログ取得
    const res = await fetch(`/api/catalog/${encodeURIComponent(domain)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const entries = await res.json();

    // 2. IndexedDBに保存
    await catalogStore.save(domain, entries);

    // 3. 全ページをfetchしてSWキャッシュに載せる
    btn.textContent = `0 / ${entries.length}`;
    let done = 0;
    const concurrency = 3;
    let aborted = false;
    _downloadAbort = () => { aborted = true; };

    const queue = [...entries];
    async function worker() {
      while (queue.length > 0 && !aborted) {
        const entry = queue.shift();
        try {
          await fetch(`/api/cache/${encodeURIComponent(domain)}/${entry.path}`);
        } catch (e) {}
        done++;
        btn.textContent = `${done} / ${entries.length}`;
        progressFill.style.width = `${(done / entries.length * 100).toFixed(1)}%`;
      }
    }

    await Promise.all(Array.from({ length: concurrency }, () => worker()));
    _downloadAbort = null;

    if (aborted) {
      btn.textContent = '中断';
    } else {
      btn.textContent = '完了';
      btn.className = 'btn-downloaded';
    }

    loadLocalDatasets();
  } catch (e) {
    btn.textContent = 'エラー';
    btn.disabled = false;
    progressWrap.classList.add('hidden');
  }
}

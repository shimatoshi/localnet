// データセット管理

async function onDataTabOpen() {
  await loadLocalDatasets();
  if (isOnline) {
    loadServerDatasets();
  } else {
    $('server-datasets').innerHTML = '<p class="muted">オフライン</p>';
  }
}

async function loadServerDatasets() {
  const el = $('server-datasets');
  try {
    const res = await fetch('/api/datasets');
    const datasets = await res.json();
    if (datasets.length === 0) {
      el.innerHTML = '<p class="muted">データセットなし</p>';
      return;
    }
    const localList = await dbStore.listMeta();
    const localNames = new Set(localList.map(d => d.name));
    el.innerHTML = '';
    for (const ds of datasets) {
      const item = document.createElement('div');
      item.className = 'dataset-item';
      const isLocal = localNames.has(ds.name);
      item.innerHTML = `
        <div class="dataset-name">${escHtml(ds.name)}</div>
        <div class="dataset-info">${ds.page_count} ページ / ${formatSize(ds.size)}</div>
        <div class="dataset-actions">
          ${isLocal
            ? '<button class="btn-downloaded" disabled>&#10003; DL済み</button>'
            : `<button class="btn-download" data-name="${escHtml(ds.name)}">ダウンロード</button>`}
        </div>
        <div class="progress-bar-wrap hidden" data-progress="${escHtml(ds.name)}">
          <div class="progress-bar-fill"></div>
        </div>
      `;
      el.appendChild(item);
      if (!isLocal) {
        item.querySelector('.btn-download').addEventListener('click', function() {
          downloadDataset(ds.name, ds.size, this);
        });
      }
    }
  } catch (e) {
    el.innerHTML = '<p class="muted">サーバーに接続できません</p>';
  }
}

async function downloadDataset(name, totalSize, btn) {
  btn.disabled = true;
  btn.textContent = 'ダウンロード中...';
  const progressWrap = document.querySelector(`[data-progress="${name}"]`);
  const progressFill = progressWrap ? progressWrap.querySelector('.progress-bar-fill') : null;
  if (progressWrap) progressWrap.classList.remove('hidden');

  try {
    const res = await fetch(`/api/datasets/${encodeURIComponent(name)}/download`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const contentLength = res.headers.get('Content-Length');
    const total = contentLength ? parseInt(contentLength) : totalSize;
    const reader = res.body.getReader();
    const chunks = [];
    let received = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      if (total && progressFill) progressFill.style.width = Math.min(100, received / total * 100) + '%';
    }

    const buffer = new ArrayBuffer(received);
    const view = new Uint8Array(buffer);
    let offset = 0;
    for (const chunk of chunks) { view.set(chunk, offset); offset += chunk.length; }

    let meta = {};
    try {
      const sql = await initSQL();
      const tmpDb = new sql.Database(new Uint8Array(buffer));
      const rows = tmpDb.exec("SELECT key, value FROM meta");
      if (rows.length > 0) for (const row of rows[0].values) meta[row[0]] = row[1];
      tmpDb.close();
    } catch (e) {}

    await dbStore.save(name, buffer, meta);
    triggerFileDownload(buffer, `${name}.sqlite`);

    btn.textContent = '&#10003; 完了';
    btn.className = 'btn-downloaded';
    if (progressWrap) progressWrap.classList.add('hidden');
    await loadLocalDatasets();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'リトライ';
    if (progressWrap) progressWrap.classList.add('hidden');
    alert('エラー: ' + e.message);
  }
}

function triggerFileDownload(arrayBuffer, filename) {
  const blob = new Blob([arrayBuffer], { type: 'application/x-sqlite3' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
}

async function loadLocalDatasets() {
  const el = $('local-datasets');
  try {
    const datasets = await dbStore.listMeta();
    if (datasets.length === 0) {
      el.innerHTML = '<p class="muted">まだデータセットがありません</p>';
      return;
    }
    el.innerHTML = '';
    for (const ds of datasets) {
      const item = document.createElement('div');
      item.className = 'dataset-item';
      item.innerHTML = `
        <div class="dataset-name">${escHtml(ds.name)}</div>
        <div class="dataset-info">${ds.page_count || '?'} ページ / ${formatSize(ds.size_bytes)}</div>
        <div class="dataset-actions">
          <button class="btn-delete" data-name="${escHtml(ds.name)}">削除</button>
        </div>
      `;
      el.appendChild(item);
      item.querySelector('.btn-delete').addEventListener('click', async function() {
        if (!confirm(`${ds.name} を削除？`)) return;
        await dbStore.delete(ds.name);
        if (openDBs.has(ds.name)) { openDBs.get(ds.name).close(); openDBs.delete(ds.name); }
        await loadLocalDatasets();
      });
    }
  } catch (e) {
    el.innerHTML = '<p class="muted">読み込みエラー</p>';
  }
}

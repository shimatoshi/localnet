// 検索 — Web検索 + 画像検索

function sanitizeSnippet(s) {
  const placeholder = '\x00B\x00';
  const placeholderEnd = '\x00/B\x00';
  s = s.replace(/<b>/g, placeholder).replace(/<\/b>/g, placeholderEnd);
  s = escHtml(s);
  s = s.replace(/\x00B\x00/g, '<b>').replace(/\x00\/B\x00/g, '</b>');
  return s;
}

let _currentQuery = '';
let _currentMode = 'web';

window.doSearch = async function(query) {
  if (!query) return;
  _currentQuery = query;
  _currentMode = 'web';

  $('results-search').value = query;
  showScreen('screen-results');

  document.querySelectorAll('.results-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === 'web'));
  show('results-web');
  hide('results-images');

  await runWebSearch(query);
};

window.switchResultsTab = async function(mode) {
  _currentMode = mode;
  document.querySelectorAll('.results-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === mode));

  if (mode === 'web') {
    show('results-web');
    hide('results-images');
    await runWebSearch(_currentQuery);
  } else {
    hide('results-web');
    show('results-images');
    await runImageSearch(_currentQuery);
  }
};

async function runWebSearch(query) {
  const el = $('results-web');
  el.innerHTML = '<p class="muted" style="padding:20px">検索中...</p>';

  try {
    const dsList = await dbStore.listMeta();
    if (dsList.length === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px">データセットがありません。メニューからダウンロードしてください。</p>';
      return;
    }

    const results = await searchAll(query);
    if (results.length === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px">結果なし</p>';
      return;
    }

    el.innerHTML = '';
    results.forEach(r => {
      const item = document.createElement('div');
      item.className = 'result-item';
      item.innerHTML = `
        <div class="result-site">${escHtml(r.domain || r.dataset)}</div>
        <div class="result-title">${escHtml(r.title || '(無題)')}</div>
        <div class="result-snippet">${sanitizeSnippet(r.snippet || '')}</div>
      `;
      item.addEventListener('click', () => openInBrowser(r.dataset, r.id, r.url));
      el.appendChild(item);
    });
  } catch (e) {
    el.innerHTML = `<p class="muted" style="padding:20px">エラー: ${escHtml(e.message)}</p>`;
  }
}

async function runImageSearch(query) {
  const el = $('results-images');
  el.innerHTML = '<p class="muted" style="padding:20px;width:100%">検索中...</p>';

  try {
    const datasets = await dbStore.listMeta();
    if (datasets.length === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px;width:100%">データセットなし</p>';
      return;
    }

    await initSQL();
    const results = [];

    for (const ds of datasets) {
      const db = await openDataset(ds.name);
      if (!db) continue;
      try {
        // pages_ftsで検索 → そのページに紐づく画像を取得
        const stmt = db.prepare(`
          SELECT DISTINCT i.id as img_id, i.mime, p.title, p.url, p.id as page_id
          FROM pages_fts
          JOIN pages p ON p.id = pages_fts.rowid
          JOIN images i
          WHERE pages_fts MATCH ?
          AND p.content_html LIKE '%localnet://img/' || i.id || '%'
          LIMIT 30
        `);
        stmt.bind([query]);
        while (stmt.step()) {
          const row = stmt.getAsObject();
          row.dataset = ds.name;
          results.push(row);
        }
        stmt.free();
      } catch (e) {
        // FTSなしフォールバック: LIKE検索
        try {
          const stmt = db.prepare(`
            SELECT DISTINCT i.id as img_id, i.mime, p.title, p.url, p.id as page_id
            FROM pages p
            JOIN images i
            WHERE (p.title LIKE '%' || ? || '%' OR p.content_text LIKE '%' || ? || '%')
            AND p.content_html LIKE '%localnet://img/' || i.id || '%'
            LIMIT 30
          `);
          stmt.bind([query, query]);
          while (stmt.step()) {
            const row = stmt.getAsObject();
            row.dataset = ds.name;
            results.push(row);
          }
          stmt.free();
        } catch (e2) {}
      }
    }

    if (results.length === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px;width:100%">画像なし</p>';
      return;
    }

    el.innerHTML = '';
    for (const r of results.slice(0, 60)) {
      const div = document.createElement('div');
      div.className = 'img-result';
      // 画像をBlobURLで読み込み
      const db = await openDataset(r.dataset);
      let stmt;
      try {
        stmt = db.prepare('SELECT data, mime FROM images WHERE id = ?');
        stmt.bind([r.img_id]);
        if (stmt.step()) {
          const row = stmt.getAsObject(null);
          if (row.data instanceof Uint8Array) {
            const blob = new Blob([row.data], { type: row.mime || r.mime || 'image/jpeg' });
            const url = URL.createObjectURL(blob);
            const img = document.createElement('img');
            img.src = url;
            img.loading = 'lazy';
            div.appendChild(img);
          }
        }
      } finally {
        if (stmt) stmt.free();
      }

      div.addEventListener('click', () => openInBrowser(r.dataset, r.page_id, r.url));
      el.appendChild(div);
    }
  } catch (e) {
    el.innerHTML = `<p class="muted" style="padding:20px;width:100%">エラー: ${escHtml(e.message)}</p>`;
  }
}

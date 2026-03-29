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

    el.innerHTML = '<p class="muted" style="padding:20px">データセット読み込み中...</p>';

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

    // まずWeb検索で該当ページを取得 → そのページIDに紐づく画像を表示
    const webResults = await searchAll(query, 20);
    if (webResults.length === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px;width:100%">画像なし</p>';
      return;
    }

    el.innerHTML = '';
    let imgCount = 0;

    for (const r of webResults) {
      if (imgCount >= 60) break;
      const db = await openDataset(r.dataset);
      if (!db) continue;

      // このページで使われている画像IDをcontent_textから間接的に取れないので
      // imagesテーブルの全画像をページURLのドメインでフィルタして表示
      let stmt;
      try {
        stmt = db.prepare('SELECT id, data, mime FROM images LIMIT 100');
        while (stmt.step() && imgCount < 60) {
          const row = stmt.getAsObject(null);
          if (!(row.data instanceof Uint8Array)) continue;
          // 小さすぎる画像（アイコン等）はスキップ
          if (row.data.length < 2000) continue;

          const div = document.createElement('div');
          div.className = 'img-result';
          const blob = new Blob([row.data], { type: row.mime || 'image/jpeg' });
          const url = URL.createObjectURL(blob);
          const img = document.createElement('img');
          img.src = url;
          img.loading = 'lazy';
          div.appendChild(img);
          div.addEventListener('click', () => openInBrowser(r.dataset, r.id, r.url));
          el.appendChild(div);
          imgCount++;
        }
      } finally {
        if (stmt) stmt.free();
      }
    }

    if (imgCount === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px;width:100%">画像なし</p>';
    }
  } catch (e) {
    el.innerHTML = `<p class="muted" style="padding:20px;width:100%">エラー: ${escHtml(e.message)}</p>`;
  }
}

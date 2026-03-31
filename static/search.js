// 検索 — サーバーAPI経由タイトル検索

let _currentQuery = '';

window.doSearch = async function(query) {
  if (!query) return;
  _currentQuery = query;

  $('results-search').value = query;
  showScreen('screen-results');

  await runWebSearch(query);
};

async function runWebSearch(query) {
  const el = $('results-web');
  el.innerHTML = '<p class="muted" style="padding:20px">検索中...</p>';

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=50`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const results = await res.json();

    if (results.length === 0) {
      el.innerHTML = '<p class="muted" style="padding:20px">結果なし</p>';
      return;
    }

    el.innerHTML = '';
    results.forEach(r => {
      const item = document.createElement('div');
      item.className = 'result-item';
      item.innerHTML = `
        <div class="result-site">${escHtml(r.domain)}</div>
        <div class="result-title">${escHtml(r.title || '(無題)')}</div>
        <div class="result-snippet">${escHtml(r.url)}</div>
      `;
      item.addEventListener('click', () => openInBrowser(r.url));
      el.appendChild(item);
    });
  } catch (e) {
    el.innerHTML = `<p class="muted" style="padding:20px">エラー: ${escHtml(e.message)}</p>`;
  }
}

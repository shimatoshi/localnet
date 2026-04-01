// 検索 — オンライン時はサーバーAPI、オフライン時はローカルカタログ

let _currentQuery = '';

window.doSearch = async function(query) {
  if (!query) return;
  _currentQuery = query;

  $('results-search').value = query;
  showScreen('screen-results');

  await runSearch(query);
};

async function runSearch(query) {
  const el = $('results-web');
  el.innerHTML = '<p class="muted" style="padding:20px">検索中...</p>';

  try {
    let results;
    if (isOnline) {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=50`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      results = await res.json();
    } else {
      results = await catalogStore.search(query, 50);
    }

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
    // サーバーエラー時もローカル検索にフォールバック
    try {
      const results = await catalogStore.search(query, 50);
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
    } catch (e2) {
      el.innerHTML = `<p class="muted" style="padding:20px">エラー: ${escHtml(e.message)}</p>`;
    }
  }
}

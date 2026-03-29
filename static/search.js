// 検索タブ

async function onSearchTabOpen() {
  const datasets = await dbStore.listMeta();
  if (datasets.length === 0) {
    show('search-empty');
    $('search-results').innerHTML = '';
  } else {
    hide('search-empty');
  }
}

window.doSearch = async function() {
  const query = $('search-input').value.trim();
  if (!query) return;

  const resultsEl = $('search-results');
  resultsEl.innerHTML = '<p class="muted">検索中...</p>';
  hide('search-empty');

  try {
    // デバッグ: データセット状態確認
    const dsList = await dbStore.listMeta();
    console.log('Local datasets:', dsList.length, dsList.map(d => d.name));

    const results = await searchAll(query);
    console.log('Search results:', results.length);

    if (results.length === 0) {
      const info = dsList.length === 0
        ? 'データセットがダウンロードされていません'
        : `${dsList.length}個のデータセットを検索しましたが結果がありません`;
      resultsEl.innerHTML = `<p class="muted">${info}</p>`;
      return;
    }

    resultsEl.innerHTML = '';
    results.forEach(r => {
      const item = document.createElement('div');
      item.className = 'search-result';
      item.innerHTML = `
        <div class="result-title">${escHtml(r.title || '(無題)')}</div>
        <div class="result-url">${escHtml(r.url)}</div>
        <div class="result-snippet">${r.snippet || ''}</div>
        <div class="result-dataset">${escHtml(r.dataset)}</div>
      `;
      item.addEventListener('click', () => {
        openViewer(r.dataset, r.id, r.url);
      });
      resultsEl.appendChild(item);
    });
  } catch (e) {
    resultsEl.innerHTML = `<p class="muted">検索エラー: ${escHtml(e.message)}</p>`;
  }
};

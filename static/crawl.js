// クロール管理

let crawlTargetUrl = '';

function onCrawlTabOpen() {
  if (isOnline) {
    hide('crawl-offline');
    show('crawl-online');
    loadSites();
  } else {
    show('crawl-offline');
    hide('crawl-online');
  }
}

window.selectTarget = function() {
  const url = $('crawl-url').value.trim();
  if (!url) return;
  let normalized = url;
  if (!normalized.startsWith('http')) normalized = 'https://' + normalized;
  crawlTargetUrl = normalized;
  $('crawl-url').value = normalized;
  $('crawl-target').textContent = normalized;
  show('crawl-config');
};

window.doCrawl = async function() {
  const url = crawlTargetUrl || $('crawl-url').value.trim();
  if (!url) return;
  const depth = parseInt($('crawl-depth').value) || 2;
  const delay = parseFloat($('crawl-delay').value) || 1.0;
  const dailyLimit = parseInt($('crawl-limit').value) || 5000;
  const excludeStr = $('crawl-exclude').value.trim();
  const exclude = excludeStr ? excludeStr.split(',').map(s => s.trim()).filter(Boolean) : [];
  const autoBuild = $('crawl-autobuild').checked;

  $('btn-crawl').disabled = true;
  clearLog();
  show('progress-section');

  try {
    const res = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, depth, delay, daily_limit: dailyLimit, exclude, auto_build: autoBuild }),
    });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); $('btn-crawl').disabled = false; return; }
    addLog(`ジョブ開始: ${data.job_id}`);
    listenSSE(data.job_id, () => { $('btn-crawl').disabled = false; loadSites(); });
  } catch (e) {
    addLog('エラー: ' + e.message);
    $('btn-crawl').disabled = false;
  }
};

async function loadSites() {
  try {
    const res = await fetch('/api/sites');
    renderSites(await res.json());
  } catch (e) {
    $('sites-list').innerHTML = '<p class="muted">取得エラー</p>';
  }
}

function renderSites(sites) {
  const list = $('sites-list');
  if (sites.length === 0) { list.innerHTML = '<p class="muted">なし</p>'; return; }
  list.innerHTML = '';
  sites.forEach(site => {
    const item = document.createElement('div');
    item.className = 'site-item';
    let actions = '';
    if (!site.has_dataset) {
      actions = `<button class="btn-build" data-domain="${escHtml(site.domain)}">ビルド</button>`;
    } else {
      actions = `<button class="btn-downloaded" disabled>&#10003; ${formatSize(site.dataset_size)}</button>`;
    }
    item.innerHTML = `
      <div class="site-domain">${escHtml(site.domain)}</div>
      <div class="site-stats">${site.file_count} ファイル</div>
      <div class="site-actions">${actions}</div>
    `;
    list.appendChild(item);
    const btn = item.querySelector('.btn-build');
    if (btn) btn.addEventListener('click', function() { doBuild(this.dataset.domain); });
  });
}

async function doBuild(domain) {
  clearLog();
  show('progress-section');
  try {
    const res = await fetch(`/api/build/${encodeURIComponent(domain)}`, { method: 'POST' });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); return; }
    addLog(`ビルド: ${data.job_id}`);
    listenSSE(data.job_id, () => { loadSites(); });
  } catch (e) {
    addLog('エラー: ' + e.message);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  $('crawl-url').addEventListener('keydown', e => { if (e.key === 'Enter') selectTarget(); });
});

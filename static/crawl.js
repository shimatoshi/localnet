// クロール管理

let crawlTargetUrl = '';
let _currentCrawlJobId = null;

function onCrawlTabOpen() {
  if (isOnline) {
    hide('crawl-offline');
    show('crawl-online');
    loadSites();
    checkActiveJobs();
  } else {
    show('crawl-offline');
    hide('crawl-online');
  }
}

async function checkActiveJobs() {
  // 実行中ジョブがあればログ表示 & SSE再接続
  if (_currentCrawlJobId) return; // 既に接続中
  try {
    const res = await fetch('/api/jobs/active');
    const jobs = await res.json();
    if (jobs.length > 0) {
      const job = jobs[0];
      _currentCrawlJobId = job.job_id;
      show('progress-section');
      show('btn-stop');
      $('btn-crawl').disabled = true;
      addLog(`実行中のジョブに再接続: ${job.job_id} (${job.domain || ''})`);
      listenSSE(job.job_id, () => {
        $('btn-crawl').disabled = false;
        hide('btn-stop');
        _currentCrawlJobId = null;
        loadSites();
      });
    }
  } catch (e) {}
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
  const depth = parseInt($('crawl-depth').value) || 0;
  const delay = parseFloat($('crawl-delay').value) || 1.0;
  const excludeStr = $('crawl-exclude').value.trim();
  const exclude = excludeStr ? excludeStr.split(',').map(s => s.trim()).filter(Boolean) : [];
  const autoBuild = $('crawl-autobuild').checked;

  $('btn-crawl').disabled = true;
  show('btn-stop');
  clearLog();
  show('progress-section');

  try {
    const res = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, depth, delay, exclude, auto_build: autoBuild }),
    });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); $('btn-crawl').disabled = false; hide('btn-stop'); return; }
    _currentCrawlJobId = data.job_id;
    addLog(`クロール開始: ${data.job_id} (深さ: ${depth === 0 ? '無制限' : depth})`);
    listenSSE(data.job_id, () => {
      $('btn-crawl').disabled = false;
      hide('btn-stop');
      _currentCrawlJobId = null;
      loadSites();
    });
  } catch (e) {
    addLog('エラー: ' + e.message);
    $('btn-crawl').disabled = false;
    hide('btn-stop');
  }
};

window.stopCrawl = async function() {
  if (!_currentCrawlJobId) return;
  try {
    await fetch(`/api/jobs/${_currentCrawlJobId}/stop`, { method: 'POST' });
    addLog('停止リクエスト送信...');
  } catch (e) {
    addLog('停止エラー: ' + e.message);
  }
};

window.doResume = async function(domain) {
  clearLog();
  show('progress-section');
  show('btn-stop');

  try {
    const res = await fetch(`/api/resume/${encodeURIComponent(domain)}`, { method: 'POST' });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); hide('btn-stop'); return; }
    _currentCrawlJobId = data.job_id;
    addLog(`再開: ${data.job_id} (${domain})`);
    listenSSE(data.job_id, () => {
      hide('btn-stop');
      _currentCrawlJobId = null;
      loadSites();
    });
  } catch (e) {
    addLog('エラー: ' + e.message);
    hide('btn-stop');
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
    let actions = `<button class="btn-resume" data-domain="${escHtml(site.domain)}">再開</button>`;
    if (!site.has_dataset) {
      actions += `<button class="btn-build" data-domain="${escHtml(site.domain)}">ビルド</button>`;
    } else {
      actions += `<button class="btn-downloaded" disabled>&#10003; ${formatSize(site.dataset_size)}</button>`;
      actions += `<button class="btn-build" data-domain="${escHtml(site.domain)}">再ビルド</button>`;
    }
    item.innerHTML = `
      <div class="site-domain">${escHtml(site.domain)}</div>
      <div class="site-stats">${site.file_count} ファイル</div>
      <div class="site-actions">${actions}</div>
    `;
    list.appendChild(item);
    item.querySelector('.btn-resume').addEventListener('click', function() { doResume(this.dataset.domain); });
    item.querySelectorAll('.btn-build').forEach(btn => {
      btn.addEventListener('click', function() { doBuild(this.dataset.domain); });
    });
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

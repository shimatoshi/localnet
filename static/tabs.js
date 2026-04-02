// タブ管理 + ナビゲーション

let tabs = [];
let activeTabIndex = 0;
let _tabIdCounter = 0;

function createTab() {
  const tab = {
    id: ++_tabIdCounter,
    title: '新しいタブ',
    url: '',
    historyStack: [],
    historyPos: -1,
  };
  tabs.push(tab);
  activeTabIndex = tabs.length - 1;
  updateTabCount();
  return tab;
}

function updateTabCount() {
  $('tab-count').textContent = tabs.length || 1;
}

window.addNewTab = function() {
  createTab();
  goHome();
};

window.showTabs = function() {
  showScreen('screen-tabs');
};

function renderTabs() {
  const el = $('tabs-list');
  if (tabs.length === 0) {
    el.innerHTML = '<p class="muted" style="padding:40px 16px;text-align:center">タブなし</p>';
    return;
  }
  el.innerHTML = '';
  tabs.forEach((tab, i) => {
    const card = document.createElement('div');
    card.className = 'tab-card' + (i === activeTabIndex ? ' active-tab' : '');
    card.innerHTML = `
      <div class="tab-title">${escHtml(tab.title || '新しいタブ')}</div>
      <button class="tab-close" data-idx="${i}">&times;</button>
    `;
    card.addEventListener('click', (e) => {
      if (e.target.classList.contains('tab-close')) return;
      activeTabIndex = i;
      if (tab.url) {
        showScreen('screen-browser');
        restoreTab(tab);
      } else {
        goHome();
      }
    });
    card.querySelector('.tab-close').addEventListener('click', () => {
      tabs.splice(i, 1);
      if (tabs.length === 0) {
        activeTabIndex = 0;
        goHome();
      } else {
        activeTabIndex = Math.min(activeTabIndex, tabs.length - 1);
        renderTabs();
      }
      updateTabCount();
    });
    el.appendChild(card);
  });
}

function currentTab() {
  if (tabs.length === 0) createTab();
  return tabs[activeTabIndex];
}

// ========== ナビゲーション ==========

function navigateTo(url, title) {
  const tab = currentTab();
  tab.historyStack = tab.historyStack.slice(0, tab.historyPos + 1);
  tab.historyStack.push({ url, title });
  tab.historyPos = tab.historyStack.length - 1;
  tab.url = url;
  tab.title = title || url;
  updateNavButtons();
}

function updateNavButtons() {
  const tab = currentTab();
  $('btn-back').disabled = tab.historyPos <= 0;
  $('btn-forward').disabled = tab.historyPos >= tab.historyStack.length - 1;
}

window.browserBack = function() {
  const tab = currentTab();
  if (tab.historyPos > 0) {
    tab.historyPos--;
    const entry = tab.historyStack[tab.historyPos];
    tab.url = entry.url;
    tab.title = entry.title;
    loadPage(entry.url, false);
  }
};

window.browserForward = function() {
  const tab = currentTab();
  if (tab.historyPos < tab.historyStack.length - 1) {
    tab.historyPos++;
    const entry = tab.historyStack[tab.historyPos];
    tab.url = entry.url;
    tab.title = entry.title;
    loadPage(entry.url, false);
  }
};

function restoreTab(tab) {
  if (tab.historyPos >= 0) {
    const entry = tab.historyStack[tab.historyPos];
    loadPage(entry.url, false);
  }
}

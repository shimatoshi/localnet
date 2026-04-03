/**
 * ビルド後にdist/sw.jsのAPP_SHELLにassetファイルリストを注入する
 * npm run build の後に実行: node inject-sw-assets.js
 */
const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, 'dist');
const swPath = path.join(distDir, 'sw.js');

if (!fs.existsSync(swPath)) {
  console.error('dist/sw.js not found. Run vite build first.');
  process.exit(1);
}

// dist/assets/ 内のファイルを列挙
const assetsDir = path.join(distDir, 'assets');
const assetFiles = fs.existsSync(assetsDir)
  ? fs.readdirSync(assetsDir).map(f => `/assets/${f}`)
  : [];

const appShell = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.png',
  '/sw.js',
  ...assetFiles,
];

// SW内の self.__APP_SHELL || [...] をassetリストで置換
let sw = fs.readFileSync(swPath, 'utf-8');
sw = sw.replace(
  /const APP_SHELL = self\.__APP_SHELL \|\| \[[\s\S]*?\];/,
  `const APP_SHELL = ${JSON.stringify(appShell, null, 2)};`
);

// キャッシュバージョンにビルドハッシュを含める
const buildHash = assetFiles.length > 0
  ? assetFiles[0].match(/-([a-zA-Z0-9]+)\./)?.[1] || Date.now()
  : Date.now();
sw = sw.replace(
  /const CACHE_NAME = '[^']+'/,
  `const CACHE_NAME = 'localnet-v13-${buildHash}'`
);

fs.writeFileSync(swPath, sw);
console.log(`SW injected: ${appShell.length} files, cache=${buildHash}`);

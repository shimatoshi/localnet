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

// CACHE_NAMEはsw.jsで定義された固定値をそのまま使う
// ビルドごとに変えるとactivate時に旧キャッシュ（DL済みサイトデータ）が消える

fs.writeFileSync(swPath, sw);
console.log(`SW injected: ${appShell.length} files`);

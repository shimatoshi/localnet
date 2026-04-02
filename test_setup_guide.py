"""セットアップガイド検証テスト
SETUP.md に書いた手順が実際に動くかを確認する"""

import os
import sys
import io
import json
import time
import shutil
import sqlite3
import tarfile
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

PASS = 0
FAIL = 0

def ok(msg):
    global PASS; PASS += 1
    print(f"  PASS: {msg}")
def ng(msg):
    global FAIL; FAIL += 1
    print(f"  FAIL: {msg}")
def check(cond, msg):
    ok(msg) if cond else ng(msg)


# ======================================
# ガイド: 前提条件の確認
# ======================================
print("\n=== 前提条件の確認 ===")

# Python 3
r = subprocess.run(['python3', '--version'], capture_output=True, text=True)
check(r.returncode == 0, f"Python3 インストール済み: {r.stdout.strip()}")

# wget
r = subprocess.run(['wget', '--version'], capture_output=True, text=True)
check(r.returncode == 0, f"wget インストール済み: {r.stdout.splitlines()[0] if r.stdout else '?'}")

# Flask
try:
    import flask
    check(True, f"Flask インストール済み: {flask.__version__}")
except ImportError:
    ng("Flask がインストールされていない")

# requirements.txt の存在
check(os.path.exists('requirements.txt'), "requirements.txt が存在する")
with open('requirements.txt') as f:
    content = f.read()
    check('Flask' in content, "requirements.txt に Flask が含まれる")


# ======================================
# ガイド: 起動と動作確認
# ======================================
print("\n=== 起動と動作確認 ===")

from server import app
client = app.test_client()

res = client.get('/')
check(res.status_code == 200, f"GET / → {res.status_code} (ホーム画面)")
check(b'localnet' in res.data.lower() or b'<html' in res.data.lower(),
      "ホーム画面がHTMLを返す")


# ======================================
# ガイド: スクレイピング → データセット構築の全フロー
# ======================================
print("\n=== スクレイピング → データセット構築フロー ===")

# ガイド「方法3: cache/ にファイルを直接置く」をテスト
TEST_DOMAIN = "guide-test.local"
cache_path = f"cache/{TEST_DOMAIN}/{TEST_DOMAIN}"
os.makedirs(cache_path, exist_ok=True)

# テスト用HTMLを配置（ガイドの「手動配置」パターン）
pages = {
    "index.html": """<!DOCTYPE html>
<html><head><title>Guide Test - Home</title></head>
<body>
<h1>Welcome</h1>
<p>This is a test site created following the SETUP guide.</p>
<p>It covers Python programming and web development topics.</p>
<a href="/about.html">About</a>
<a href="/docs/tutorial.html">Tutorial</a>
</body></html>""",

    "about.html": """<!DOCTYPE html>
<html><head><title>Guide Test - About</title></head>
<body>
<h1>About This Site</h1>
<p>Created to verify the localnet setup guide works correctly.</p>
</body></html>""",

    "docs/tutorial.html": """<!DOCTYPE html>
<html><head><title>Guide Test - Tutorial</title></head>
<body>
<h1>Getting Started Tutorial</h1>
<p>Step 1: Install Termux from F-Droid.</p>
<p>Step 2: Run setup.sh to install dependencies.</p>
<p>Step 3: Start the server with python3 server.py.</p>
</body></html>""",
}

for path, content in pages.items():
    full = os.path.join(cache_path, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)
ok(f"テスト用ファイルを cache/ に配置 ({len(pages)} ページ)")

# ガイド: Crawl タブ → Sites → Build と同じAPI
res = client.post(f'/api/build/{TEST_DOMAIN}')
check(res.status_code == 200, f"POST /api/build/{TEST_DOMAIN} → {res.status_code}")
job = res.get_json()
check('job_id' in job, f"ビルドジョブ開始: {job.get('job_id')}")

# ジョブ完了待ち
if 'job_id' in job:
    for _ in range(30):
        time.sleep(0.5)
        r = client.get(f"/api/jobs/{job['job_id']}")
        status = r.get_json()
        if status['status'] in ('done', 'error'):
            break
    check(status['status'] == 'done', f"ビルドジョブ完了: {status['status']}")
    if status.get('error'):
        ng(f"  エラー詳細: {status['error']}")

# データセット確認
ds_path = f"datasets/{TEST_DOMAIN}.sqlite"
check(os.path.exists(ds_path), "データセットファイルが生成された")

conn = sqlite3.connect(ds_path)
page_count = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
check(page_count == 3, f"ページ数 = {page_count} (期待: 3)")

# FTS5検索テスト
fts = conn.execute("""
    SELECT pages.title FROM pages_fts
    JOIN pages ON pages.id = pages_fts.rowid
    WHERE pages_fts MATCH 'Python'
""").fetchall()
check(len(fts) > 0, f"FTS5 'Python' → {len(fts)} 件ヒット")

fts2 = conn.execute("""
    SELECT pages.title FROM pages_fts
    JOIN pages ON pages.id = pages_fts.rowid
    WHERE pages_fts MATCH 'Tutorial'
""").fetchall()
check(len(fts2) > 0, f"FTS5 'Tutorial' → {len(fts2)} 件ヒット")

# メタデータ
meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
check(meta.get('page_count') == '3', f"meta page_count = {meta.get('page_count')}")
conn.close()


# ======================================
# ガイド: 検索インデックス
# ======================================
print("\n=== 検索インデックス確認 ===")

idx_path = "datasets/search_index.sqlite"
check(os.path.exists(idx_path), "search_index.sqlite が存在する")

conn = sqlite3.connect(idx_path)
# ガイドテストドメインが含まれるか
datasets_in_idx = [r[0] for r in conn.execute("SELECT DISTINCT dataset FROM pages")]
check(TEST_DOMAIN in datasets_in_idx, f"検索インデックスにテストドメインが含まれる")

# テキスト横断検索
results = conn.execute("""
    SELECT p.title, p.dataset FROM pages_fts
    JOIN pages p ON p.id = pages_fts.rowid
    WHERE pages_fts MATCH 'Python'
""").fetchall()
check(len(results) > 0, f"横断検索 'Python' → {len(results)} 件")

# 複数データセットにまたがる結果か
datasets_in_results = set(r[1] for r in results)
check(len(datasets_in_results) >= 1, f"検索結果のデータセット数: {len(datasets_in_results)}")
conn.close()


# ======================================
# ガイド: エクスポート → インポート
# ======================================
print("\n=== エクスポート → インポート フロー ===")

# エクスポート
res = client.get(f'/api/export/{TEST_DOMAIN}')
check(res.status_code == 200, "エクスポート成功")
tar_data = res.data
check(len(tar_data) > 0, f"エクスポートサイズ: {len(tar_data)} bytes")

# tar.gz の中身確認
with tarfile.open(fileobj=io.BytesIO(tar_data), mode='r:gz') as tar:
    names = tar.getnames()
    html_files = [n for n in names if n.endswith('.html')]
    check(len(html_files) == 3, f"tar.gz内のHTMLファイル数: {len(html_files)}")

# インポート先を別ドメインとしてシミュレート
IMPORT_DOMAIN = "imported-guide.local"
import_tar = io.BytesIO()
with tarfile.open(fileobj=import_tar, mode='w:gz') as tar:
    for path, content in pages.items():
        data = content.encode('utf-8')
        info = tarfile.TarInfo(name=f"{IMPORT_DOMAIN}/{IMPORT_DOMAIN}/{path}")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
import_tar.seek(0)

res = client.post('/api/import',
    data={'file': (import_tar, f'{IMPORT_DOMAIN}.tar.gz')},
    content_type='multipart/form-data',
)
check(res.status_code == 200, f"インポートAPI → {res.status_code}")
job = res.get_json()

if 'job_id' in job:
    for _ in range(30):
        time.sleep(0.5)
        r = client.get(f"/api/jobs/{job['job_id']}")
        s = r.get_json()
        if s['status'] in ('done', 'error'):
            break
    check(s['status'] == 'done', f"インポートジョブ完了: {s['status']}")

# インポート後に検索可能か
import_ds = f"datasets/{IMPORT_DOMAIN}.sqlite"
check(os.path.exists(import_ds), "インポートされたデータセットが存在")

conn = sqlite3.connect(import_ds)
cnt = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
check(cnt == 3, f"インポートされたページ数: {cnt}")
conn.close()

# 検索インデックスに含まれるか
conn = sqlite3.connect(idx_path)
imported_in_idx = conn.execute(
    "SELECT count(*) FROM pages WHERE dataset = ?", (IMPORT_DOMAIN,)
).fetchone()[0]
check(imported_in_idx == 3, f"インポート分が検索インデックスに反映: {imported_in_idx} 件")
conn.close()


# ======================================
# ガイド: データセット一覧API
# ======================================
print("\n=== データセットAPI確認 ===")

res = client.get('/api/datasets')
datasets = res.get_json()
names = [d['name'] for d in datasets]
check(TEST_DOMAIN in names, f"ビルドしたデータセットが一覧に含まれる")
check(IMPORT_DOMAIN in names, f"インポートしたデータセットが一覧に含まれる")

# 各データセットにpage_countが正しく入っているか
for d in datasets:
    if d['name'] == TEST_DOMAIN:
        check(d['page_count'] == 3, f"{TEST_DOMAIN} の page_count = {d['page_count']}")
    if d['name'] == IMPORT_DOMAIN:
        check(d['page_count'] == 3, f"{IMPORT_DOMAIN} の page_count = {d['page_count']}")


# ======================================
# ガイド: FAQ確認 — ファイル構成
# ======================================
print("\n=== ファイル構成確認 ===")

required_files = [
    'server.py', 'crawler.py', 'dataset_builder.py', 'jobs.py',
    'config.py', 'requirements.txt', 'setup.sh', 'SETUP.md',
    'static/index.html', 'static/style.css', 'static/app.js',
    'static/db.js', 'static/sqldb.js', 'static/search.js',
    'static/datasets.js', 'static/viewer.js', 'static/crawl.js',
]
for f in required_files:
    check(os.path.exists(f), f"必要ファイル存在: {f}")


# ======================================
# ガイド: 配布パッケージ検証
# ======================================
print("\n=== 配布パッケージ検証 ===")

# build_dist.sh で作ったtar.gzが正しいか
dist_files = [f for f in os.listdir('.') if f.startswith('localnet-') and f.endswith('.tar.gz')]
if dist_files:
    dist = dist_files[0]
    with tarfile.open(dist, 'r:gz') as tar:
        names = tar.getnames()
        # 必要ファイルが全部含まれるか
        check(any('server.py' in n for n in names), f"配布パッケージに server.py 含む")
        check(any('crawler.py' in n for n in names), f"配布パッケージに crawler.py 含む")
        check(any('setup.sh' in n for n in names), f"配布パッケージに setup.sh 含む")
        check(any('SETUP.md' in n for n in names), f"配布パッケージに SETUP.md 含む")
        check(any('index.html' in n for n in names), f"配布パッケージに index.html 含む")
        # cache/datasets は含まれないこと
        check(not any('/cache/' in n for n in names), "配布パッケージに cache/ 含まない")
        check(not any('/datasets/' in n for n in names), "配布パッケージに datasets/ 含まない")
        check(not any('test_' in n for n in names), "配布パッケージにテストファイル含まない")
    ok(f"配布パッケージ検証完了: {dist}")
else:
    ng("配布パッケージが見つからない (build_dist.sh を先に実行)")


# ======================================
# クリーンアップ
# ======================================
print("\n=== クリーンアップ ===")

for domain in [TEST_DOMAIN, IMPORT_DOMAIN]:
    ds = f"datasets/{domain}.sqlite"
    if os.path.exists(ds):
        os.remove(ds)
    cache = f"cache/{domain}"
    if os.path.isdir(cache):
        shutil.rmtree(cache)

# 検索インデックス再構築
from dataset_builder import update_search_index
update_search_index()
ok("テストデータ削除完了")


# ======================================
# 結果
# ======================================
print(f"\n{'='*50}")
print(f"結果: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    sys.exit(1)
else:
    print("All tests passed! ガイドの手順はすべて正常に動作します。")

"""E2Eテスト: クロール → データセット構築 → 検索インデックス → API確認"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import CACHE_BASE, DATASETS_DIR
from dataset_builder import DatasetBuilder, update_search_index, SEARCH_INDEX_FILE

PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  PASS: {msg}")

def ng(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL: {msg}")

def check(cond, msg):
    if cond:
        ok(msg)
    else:
        ng(msg)


# === Phase 1: テスト用HTMLキャッシュを作成 ===
print("\n=== Phase 1: テスト用キャッシュ作成 ===")

TEST_DOMAIN = "test-e2e.local"
cache_dir = os.path.join(CACHE_BASE, TEST_DOMAIN, TEST_DOMAIN)
os.makedirs(cache_dir, exist_ok=True)

# ページ1: index.html
with open(os.path.join(cache_dir, "index.html"), "w") as f:
    f.write("""<!DOCTYPE html>
<html><head><title>テストサイト トップ</title></head>
<body>
<h1>テストサイトへようこそ</h1>
<p>これは全文検索のテストページです。Python、機械学習、データサイエンスについて。</p>
<img src="/images/logo.png">
<a href="/about.html">About</a>
</body></html>""")

# ページ2: about.html
with open(os.path.join(cache_dir, "about.html"), "w") as f:
    f.write("""<!DOCTYPE html>
<html><head><title>テストサイト About</title></head>
<body>
<h1>About</h1>
<p>このサイトはローカルネットの検索機能をテストするために作られました。</p>
<p>SQLite FTS5を使った高速な全文検索を実現しています。</p>
</body></html>""")

# ページ3: サブディレクトリ
sub_dir = os.path.join(cache_dir, "docs")
os.makedirs(sub_dir, exist_ok=True)
with open(os.path.join(sub_dir, "guide.html"), "w") as f:
    f.write("""<!DOCTYPE html>
<html><head><title>ガイド</title></head>
<body>
<h1>使い方ガイド</h1>
<p>データセットをダウンロードして、検索バーにキーワードを入力してください。</p>
</body></html>""")

# テスト用画像 (1x1 PNG)
img_dir = os.path.join(cache_dir, "images")
os.makedirs(img_dir, exist_ok=True)
import base64
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
with open(os.path.join(img_dir, "logo.png"), "wb") as f:
    f.write(PNG_1x1)

ok("テスト用HTMLキャッシュ作成完了")


# === Phase 2: データセット構築 ===
print("\n=== Phase 2: データセット構築 ===")

ds_path = os.path.join(DATASETS_DIR, f"{TEST_DOMAIN}.sqlite")
if os.path.exists(ds_path):
    os.remove(ds_path)

builder = DatasetBuilder(TEST_DOMAIN)
output = builder.build()

check(os.path.exists(output), f"データセットファイル生成: {os.path.basename(output)}")

conn = sqlite3.connect(output)
cur = conn.cursor()

page_count = cur.execute("SELECT count(*) FROM pages").fetchone()[0]
check(page_count == 3, f"ページ数 = {page_count} (期待: 3)")

img_count = cur.execute("SELECT count(*) FROM images").fetchone()[0]
check(img_count >= 1, f"画像数 = {img_count} (期待: >= 1)")

# FTS5テスト
fts_results = cur.execute("""
    SELECT p.title FROM pages_fts
    JOIN pages p ON p.id = pages_fts.rowid
    WHERE pages_fts MATCH 'Python'
""").fetchall()
check(len(fts_results) > 0, f"FTS5 'Python' 検索結果: {len(fts_results)} 件")

fts_results2 = cur.execute("""
    SELECT p.title FROM pages_fts
    JOIN pages p ON p.id = pages_fts.rowid
    WHERE pages_fts MATCH 'ガイド'
""").fetchall()
check(len(fts_results2) > 0, f"FTS5 'ガイド' 検索結果: {len(fts_results2)} 件")

# メタデータ
meta = dict(cur.execute("SELECT key, value FROM meta").fetchall())
check(meta.get('page_count') == '3', f"meta page_count = {meta.get('page_count')}")
check(meta.get('name') == TEST_DOMAIN, f"meta name = {meta.get('name')}")

# content_html がgzip圧縮されているか
import gzip
row = cur.execute("SELECT content_html FROM pages WHERE url LIKE '%index.html'").fetchone()
try:
    html = gzip.decompress(row[0]).decode('utf-8')
    check('テストサイト' in html, "content_html はgzip圧縮されている")
except Exception as e:
    ng(f"content_html gzip解凍失敗: {e}")

# 画像URLが書き換えられているか
check('localnet://img/' in html, f"画像URLが localnet://img/ に書き換え済み")

conn.close()


# === Phase 3: 検索インデックス構築 ===
print("\n=== Phase 3: 検索インデックス構築 ===")

index_path = update_search_index()
check(os.path.exists(index_path), "検索インデックスファイル生成")

conn = sqlite3.connect(index_path)
cur = conn.cursor()

# datasetカラムが正しく入っているか
datasets_in_index = [r[0] for r in cur.execute("SELECT DISTINCT dataset FROM pages").fetchall()]
check(TEST_DOMAIN in datasets_in_index, f"テストドメインがインデックスに含まれる")

# 全データセットが含まれるか
total = cur.execute("SELECT count(*) FROM pages").fetchone()[0]
check(total > 3, f"全データセットのページ数 = {total}")

# FTS5検索
results = cur.execute("""
    SELECT p.title, p.dataset FROM pages_fts
    JOIN pages p ON p.id = pages_fts.rowid
    WHERE pages_fts MATCH '検索'
    LIMIT 10
""").fetchall()
check(len(results) > 0, f"インデックスFTS5 '検索' 結果: {len(results)} 件")

# content_htmlやimageデータが含まれていないか（軽量確認）
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
check('images' not in tables, "検索インデックスにimagesテーブルなし（軽量）")

cols = [r[1] for r in cur.execute("PRAGMA table_info(pages)").fetchall()]
check('content_html' not in cols, "検索インデックスにcontent_htmlカラムなし（軽量）")

# サイズ比較
idx_size = os.path.getsize(index_path)
ds_size = os.path.getsize(ds_path)
print(f"  INFO: 検索インデックス {idx_size/1024:.0f}KB, テストデータセット {ds_size/1024:.0f}KB")

conn.close()


# === Phase 4: Flask API テスト ===
print("\n=== Phase 4: API テスト ===")

from server import app
client = app.test_client()

# データセット一覧
res = client.get('/api/datasets')
check(res.status_code == 200, f"GET /api/datasets → {res.status_code}")
datasets = res.get_json()
names = [d['name'] for d in datasets]
check(TEST_DOMAIN in names, f"テストドメインがAPI一覧に含まれる")

# データセットダウンロード
res = client.get(f'/api/datasets/{TEST_DOMAIN}/download')
check(res.status_code == 200, f"GET /api/datasets/{TEST_DOMAIN}/download → {res.status_code}")
check(len(res.data) > 0, f"ダウンロードサイズ: {len(res.data)} bytes")

# 検索インデックスダウンロード
res = client.get('/api/search-index/download')
check(res.status_code == 200, f"GET /api/search-index/download → {res.status_code}")
check(len(res.data) > 0, f"検索インデックスDLサイズ: {len(res.data)} bytes")

# ダウンロードしたインデックスが有効なSQLiteか確認
import tempfile
with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as tmp:
    tmp.write(res.data)
    tmp_path = tmp.name

try:
    conn = sqlite3.connect(tmp_path)
    count = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
    check(count > 0, f"DLした検索インデックスのページ数: {count}")
    fts_ok = conn.execute("""
        SELECT count(*) FROM pages_fts
        JOIN pages ON pages.id = pages_fts.rowid
        WHERE pages_fts MATCH 'Python'
    """).fetchone()[0]
    check(fts_ok > 0, f"DLした検索インデックスでFTS5検索成功: {fts_ok} 件")
    conn.close()
finally:
    os.unlink(tmp_path)

# 不正パスのテスト
res = client.get('/api/datasets/../../../etc/passwd/download')
check(res.status_code in (400, 404), f"パストラバーサル防止 → {res.status_code}")


# === Phase 4.5: エクスポート/インポート テスト ===
print("\n=== Phase 4.5: エクスポート/インポート テスト ===")

import io
import tarfile as tf

# エクスポート
res = client.get(f'/api/export/{TEST_DOMAIN}')
check(res.status_code == 200, f"GET /api/export/{TEST_DOMAIN} → {res.status_code}")
check(len(res.data) > 0, f"エクスポートサイズ: {len(res.data)} bytes")

# tar.gzとして有効か
tar_data = io.BytesIO(res.data)
with tf.open(fileobj=tar_data, mode='r:gz') as tar:
    members = tar.getnames()
    check(any(TEST_DOMAIN in m for m in members), f"tar.gz内にドメインディレクトリあり")
    check(any('index.html' in m for m in members), f"tar.gz内にindex.htmlあり")
    html_count = sum(1 for m in members if m.endswith('.html'))
    check(html_count == 3, f"tar.gz内のHTMLファイル数 = {html_count} (期待: 3)")

# 存在しないドメインのエクスポート
res = client.get('/api/export/nonexistent.example.com')
check(res.status_code == 404, f"存在しないドメインのエクスポート → {res.status_code}")

# 不正ドメインのエクスポート (Flaskが..を正規化→404 or ドメイン検証→400)
res = client.get('/api/export/../../../etc')
check(res.status_code in (400, 404), f"不正ドメインのエクスポート → {res.status_code}")

# インポート: テストデータを一旦消してから再インポート
IMPORT_DOMAIN = "import-test.local"
import_cache = os.path.join(CACHE_BASE, IMPORT_DOMAIN)

# テスト用tar.gzを作成
import_tar = io.BytesIO()
with tf.open(fileobj=import_tar, mode='w:gz') as tar:
    # HTMLファイルを追加
    html_content = b"""<!DOCTYPE html>
<html><head><title>Import Test Page</title></head>
<body><h1>Imported Site</h1><p>This page was imported from a tar.gz archive for testing.</p></body></html>"""
    info = tf.TarInfo(name=f"{IMPORT_DOMAIN}/{IMPORT_DOMAIN}/index.html")
    info.size = len(html_content)
    tar.addfile(info, io.BytesIO(html_content))

import_tar.seek(0)

# インポートAPI呼び出し
res = client.post('/api/import',
    data={'file': (import_tar, f'{IMPORT_DOMAIN}.tar.gz')},
    content_type='multipart/form-data',
)
data = res.get_json()
check(res.status_code == 200, f"POST /api/import → {res.status_code}")
check('job_id' in data, f"インポートジョブ開始: {data.get('job_id')}")

# ジョブ完了を待つ
if 'job_id' in data:
    job_id = data['job_id']
    for _ in range(30):
        time.sleep(0.5)
        res2 = client.get(f'/api/jobs/{job_id}')
        job_data = res2.get_json()
        if job_data['status'] in ('done', 'error'):
            break
    check(job_data['status'] == 'done', f"インポートジョブ完了: status={job_data['status']}")

    # インポートされたデータセットを確認
    import_ds_path = os.path.join(DATASETS_DIR, f"{IMPORT_DOMAIN}.sqlite")
    check(os.path.exists(import_ds_path), "インポートされたデータセットファイルが存在")

    if os.path.exists(import_ds_path):
        conn = sqlite3.connect(import_ds_path)
        cnt = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
        check(cnt == 1, f"インポートされたページ数 = {cnt} (期待: 1)")
        title = conn.execute("SELECT title FROM pages LIMIT 1").fetchone()[0]
        check(title == 'Import Test Page', f"インポートされたタイトル = {title}")
        conn.close()

    # 検索インデックスにも含まれるか
    idx_conn = sqlite3.connect(os.path.join(DATASETS_DIR, SEARCH_INDEX_FILE))
    idx_cnt = idx_conn.execute("SELECT count(*) FROM pages WHERE dataset = ?", (IMPORT_DOMAIN,)).fetchone()[0]
    check(idx_cnt == 1, f"検索インデックスにインポート分が含まれる: {idx_cnt} 件")
    idx_conn.close()

    # インポートのクリーンアップ
    if os.path.exists(import_ds_path):
        os.remove(import_ds_path)
    if os.path.isdir(import_cache):
        shutil.rmtree(import_cache)

# パストラバーサルを含むtar.gzのインポート
bad_tar = io.BytesIO()
with tf.open(fileobj=bad_tar, mode='w:gz') as tar:
    info = tf.TarInfo(name="../../../etc/evil.html")
    info.size = 5
    tar.addfile(info, io.BytesIO(b"hello"))
bad_tar.seek(0)
res = client.post('/api/import',
    data={'file': (bad_tar, 'evil.tar.gz')},
    content_type='multipart/form-data',
)
check(res.status_code == 400, f"パストラバーサルtar.gzのインポート拒否 → {res.status_code}")


# === Phase 5: クリーンアップ ===
print("\n=== Phase 5: クリーンアップ ===")

# テスト用データセット削除
os.remove(ds_path)
shutil.rmtree(os.path.join(CACHE_BASE, TEST_DOMAIN))
# インデックス再構築（テストデータ除去）
update_search_index()
ok("テストデータ削除完了")


# === 結果 ===
print(f"\n{'='*40}")
print(f"結果: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    sys.exit(1)
else:
    print("All tests passed!")

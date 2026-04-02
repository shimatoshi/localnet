#!/usr/bin/env python3
"""localnet sqlite変換器 — tar.gz からオフラインで .sqlite データセットを構築

使い方:
  python3 convert.py site.tar.gz
  python3 convert.py site.tar.gz -o output.sqlite
  python3 convert.py cache/site.com/   (ディレクトリ直接指定も可)

出力: {ドメイン名}.sqlite（FTS5全文検索・画像埋め込み済み）
依存: Python 3.8+ のみ（外部パッケージ不要）
"""

import os
import re
import sys
import gzip
import sqlite3
import tarfile
import tempfile
import mimetypes
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin, quote, unquote
from datetime import datetime, timezone


# === テキスト抽出 ===

class TextExtractor(HTMLParser):
    SKIP_TAGS = {'script', 'style', 'noscript', 'svg', 'math'}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)

    def get_text(self):
        return ' '.join(self.parts)


def extract_text(html_str):
    ex = TextExtractor()
    try:
        ex.feed(html_str)
    except Exception:
        pass
    return ex.get_text()


def extract_title(html_str):
    m = re.search(r'<title[^>]*>(.*?)</title>', html_str[:4096], re.IGNORECASE | re.DOTALL)
    return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''


# === MIME判定 ===

def detect_mime(filepath):
    try:
        with open(filepath, 'rb') as f:
            head = f.read(256)
        return detect_mime_from_bytes(head)
    except Exception:
        return None


def detect_mime_from_bytes(data):
    if data.startswith(b'\x89PNG'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'GIF8'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data.startswith(b'<svg') or data.startswith(b'<?xml'):
        return 'image/svg+xml'
    if b'<html' in data[:256].lower() or b'<!doctype' in data[:256].lower():
        return 'text/html'
    return 'application/octet-stream'


# === 画像抽出・書き換え ===

def extract_image_urls(html_str, page_url):
    urls = set()
    for m in re.finditer(r'<(?:img|amp-img)[^>]+src=["\']([^"\']+)["\']', html_str, re.IGNORECASE):
        urls.add(urljoin(page_url, m.group(1)))
    for m in re.finditer(r'srcset=["\']([^"\']+)["\']', html_str, re.IGNORECASE):
        for part in m.group(1).split(','):
            src = part.strip().split()[0]
            if src:
                urls.add(urljoin(page_url, src))
    for m in re.finditer(r'imagesrcset=["\']([^"\']+)["\']', html_str, re.IGNORECASE):
        for part in m.group(1).split(','):
            src = part.strip().split()[0]
            if src:
                urls.add(urljoin(page_url, src))
    for m in re.finditer(r'url\(["\']?([^"\')\s]+)["\']?\)', html_str):
        u = m.group(1)
        if any(u.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
            urls.add(urljoin(page_url, u))
    return urls


def rewrite_html_images(html_str, image_id_map, page_url):
    def replace_src(match):
        full = match.group(0)
        src = match.group(1)
        abs_url = urljoin(page_url, src)
        if abs_url in image_id_map:
            return full.replace(src, f'localnet://img/{image_id_map[abs_url]}')
        return full

    html_str = re.sub(r'<amp-img\b', '<img', html_str, flags=re.IGNORECASE)
    html_str = re.sub(r'</amp-img>', '</img>', html_str, flags=re.IGNORECASE)
    html_str = re.sub(r'src=["\']([^"\']+)["\']', replace_src, html_str)

    def replace_srcset(match):
        attr_name = match.group(1)
        srcset = match.group(2)
        parts = []
        for part in srcset.split(','):
            tokens = part.strip().split()
            if tokens:
                abs_url = urljoin(page_url, tokens[0])
                if abs_url in image_id_map:
                    tokens[0] = f'localnet://img/{image_id_map[abs_url]}'
                parts.append(' '.join(tokens))
        return f'{attr_name}="{", ".join(parts)}"'

    html_str = re.sub(r'((?:image)?srcset)=["\']([^"\']+)["\']', replace_srcset, html_str, flags=re.IGNORECASE)
    return html_str


# === ビルダー ===

def find_cached_file(img_url, base, cache_dir, domain):
    parsed = urlparse(img_url)
    path = unquote(parsed.path).lstrip('/')
    candidates = [
        os.path.join(base, path),
        os.path.join(cache_dir, parsed.netloc, path),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def build_dataset(domain, cache_dir, output_path):
    base = os.path.join(cache_dir, domain)
    if not os.path.exists(base):
        base = cache_dir

    print(f"データセット構築開始: {domain}")

    if os.path.exists(output_path):
        os.remove(output_path)

    conn = sqlite3.connect(output_path)
    cur = conn.cursor()

    cur.executescript('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL, domain TEXT NOT NULL,
            title TEXT, content_text TEXT, content_html BLOB, mime TEXT, fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, data BLOB NOT NULL, mime TEXT
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    ''')

    cur.execute("DROP TABLE IF EXISTS pages_fts")
    cur.execute('''CREATE VIRTUAL TABLE pages_fts USING fts5(
        title, content_text, content='pages', content_rowid='id', tokenize='unicode61'
    )''')

    cur.executescript('''
        DROP TRIGGER IF EXISTS pages_ai; DROP TRIGGER IF EXISTS pages_ad; DROP TRIGGER IF EXISTS pages_au;
    ''')
    cur.execute("DELETE FROM pages")
    cur.execute("DELETE FROM images")

    cur.executescript('''
        CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, title, content_text) VALUES (new.id, new.title, new.content_text);
        END;
        CREATE TRIGGER pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, title, content_text) VALUES ('delete', old.id, old.title, old.content_text);
        END;
        CREATE TRIGGER pages_au AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, title, content_text) VALUES ('delete', old.id, old.title, old.content_text);
            INSERT INTO pages_fts(rowid, title, content_text) VALUES (new.id, new.title, new.content_text);
        END;
    ''')

    now = datetime.now(timezone.utc).isoformat()

    # Pass 1: HTML収集
    print("Pass 1: HTML収集 & 画像URL抽出...")
    html_files = []
    all_image_urls = set()

    for root, dirs, files in os.walk(base):
        for fname in files:
            filepath = os.path.join(root, fname)
            relpath = os.path.relpath(filepath, base)
            url_path = relpath.replace(os.sep, '/')

            mime, _ = mimetypes.guess_type(filepath)
            if not mime:
                mime = detect_mime(filepath)
            if not mime or 'html' not in mime:
                continue

            try:
                with open(filepath, 'rb') as f:
                    raw = f.read()
                html_str = raw.decode('utf-8', errors='replace')
            except Exception:
                continue

            page_url = f"https://{domain}/{quote(url_path, safe='/:@!$&()*+,;=-._~')}"
            img_urls = extract_image_urls(html_str, page_url)
            all_image_urls.update(img_urls)
            html_files.append((filepath, url_path, page_url, raw, html_str))

    print(f"  HTML: {len(html_files)} ファイル, 画像URL: {len(all_image_urls)} 件")

    # Pass 2: 画像格納
    print("Pass 2: 画像格納中...")
    image_id_map = {}
    img_count = 0

    for img_url in all_image_urls:
        cached = find_cached_file(img_url, base, cache_dir, domain)
        if not cached:
            continue
        try:
            with open(cached, 'rb') as f:
                img_data = f.read()
            if len(img_data) == 0:
                continue
            img_mime = detect_mime_from_bytes(img_data)
            cur.execute('INSERT OR IGNORE INTO images (url, data, mime) VALUES (?,?,?)',
                        (img_url, img_data, img_mime))
            row = cur.execute('SELECT id FROM images WHERE url=?', (img_url,)).fetchone()
            if row:
                image_id_map[img_url] = row[0]
            img_count += 1
            if img_count % 50 == 0:
                print(f"  {img_count} 画像処理済み...")
                conn.commit()
        except Exception:
            continue

    conn.commit()
    print(f"  {img_count} 画像格納完了 ({len(image_id_map)} 件マッチ)")

    # Pass 3: ページ格納
    print("Pass 3: HTML書き換え & ページ格納...")
    page_count = 0

    for filepath, url_path, page_url, raw, html_str in html_files:
        title = extract_title(html_str)
        content_text = extract_text(html_str)
        rewritten = rewrite_html_images(html_str, image_id_map, page_url)
        content_html = gzip.compress(rewritten.encode('utf-8'), compresslevel=6)

        cur.execute(
            'INSERT INTO pages (url, domain, title, content_text, content_html, mime, fetched_at) VALUES (?,?,?,?,?,?,?)',
            (page_url, domain, title, content_text, content_html, 'text/html', now)
        )
        page_count += 1
        if page_count % 100 == 0:
            print(f"  {page_count} ページ処理済み...")
            conn.commit()

    cur.execute("INSERT OR REPLACE INTO meta VALUES ('name', ?)", (domain,))
    cur.execute("INSERT OR REPLACE INTO meta VALUES ('source_url', ?)", (f"https://{domain}/",))
    cur.execute("INSERT OR REPLACE INTO meta VALUES ('created_at', ?)", (now,))
    cur.execute("INSERT OR REPLACE INTO meta VALUES ('page_count', ?)", (str(page_count),))
    cur.execute("INSERT OR REPLACE INTO meta VALUES ('image_count', ?)", (str(img_count),))

    conn.commit()
    print("データベース最適化中...")
    conn.execute("VACUUM")
    conn.close()

    file_size = os.path.getsize(output_path)
    print(f"\u2705 完成: {output_path}")
    print(f"   {page_count} ページ, {img_count} 画像, {file_size / 1024 / 1024:.1f} MB")
    return output_path


# === メイン ===

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = sys.argv[1]
    output = None
    if '-o' in sys.argv:
        idx = sys.argv.index('-o')
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    # tar.gz の場合は展開
    if os.path.isfile(src) and (src.endswith('.tar.gz') or src.endswith('.tgz') or src.endswith('.tar')):
        print(f"アーカイブ展開中: {src}")
        tmpdir = tempfile.mkdtemp(prefix='localnet_convert_')
        try:
            mode = 'r:gz' if src.endswith(('.tar.gz', '.tgz')) else 'r:'
            with tarfile.open(src, mode) as tar:
                members = tar.getnames()
                # パストラバーサル防止
                for m in members:
                    if m.startswith('/') or '..' in m:
                        print(f"エラー: 不正なパスがアーカイブに含まれています: {m}")
                        sys.exit(1)
                tar.extractall(path=tmpdir, filter='data')

            # トップレベルディレクトリ = ドメイン名
            entries = os.listdir(tmpdir)
            if len(entries) == 1 and os.path.isdir(os.path.join(tmpdir, entries[0])):
                domain = entries[0]
                cache_dir = tmpdir
            else:
                # ドメイン名をファイル名から推定
                domain = os.path.splitext(os.path.basename(src))[0]
                if domain.endswith('.tar'):
                    domain = domain[:-4]
                cache_dir = tmpdir

            if not output:
                output = f"{domain}.sqlite"

            build_dataset(domain, cache_dir, output)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    elif os.path.isdir(src):
        # ディレクトリ直接指定
        domain = os.path.basename(os.path.normpath(src))
        parent = os.path.dirname(os.path.normpath(src))
        if not output:
            output = f"{domain}.sqlite"
        build_dataset(domain, parent, output)

    else:
        print(f"エラー: {src} が見つからないか、対応していない形式です")
        sys.exit(1)


if __name__ == '__main__':
    main()

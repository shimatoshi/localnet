"""DatasetBuilder — クロール済みHTMLからFTS5検索可能なSQLiteデータセットを構築（画像埋め込み対応）"""

import os
import re
import gzip
import sqlite3
import mimetypes
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin, quote, unquote
from datetime import datetime, timezone

from config import CACHE_BASE, DATASETS_DIR


class TextExtractor(HTMLParser):
    """HTMLからテキストを抽出（script/style除外）"""

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
    extractor = TextExtractor()
    try:
        extractor.feed(html_str)
    except Exception:
        pass
    return extractor.get_text()


def extract_title(html_str):
    m = re.search(r'<title[^>]*>(.*?)</title>', html_str[:4096], re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r'<[^>]+>', '', m.group(1)).strip()
    return ''


def detect_mime(filepath):
    try:
        with open(filepath, 'rb') as f:
            head = f.read(256)
        if head.startswith(b'\x89PNG'):
            return 'image/png'
        if head.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if head.startswith(b'GIF8'):
            return 'image/gif'
        if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
            return 'image/webp'
        if b'<html' in head.lower() or b'<!doctype' in head.lower():
            return 'text/html'
    except Exception:
        pass
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
    return 'application/octet-stream'


def extract_image_urls(html_str, page_url):
    """HTMLから全画像URLを抽出（img, amp-img, srcset, CSS background対応）"""
    urls = set()
    # <img src="...">, <amp-img src="...">
    for m in re.finditer(r'<(?:img|amp-img)[^>]+src=["\']([^"\']+)["\']', html_str, re.IGNORECASE):
        urls.add(urljoin(page_url, m.group(1)))
    # srcset
    for m in re.finditer(r'srcset=["\']([^"\']+)["\']', html_str, re.IGNORECASE):
        for part in m.group(1).split(','):
            src = part.strip().split()[0]
            if src:
                urls.add(urljoin(page_url, src))
    # imagesrcset (preload)
    for m in re.finditer(r'imagesrcset=["\']([^"\']+)["\']', html_str, re.IGNORECASE):
        for part in m.group(1).split(','):
            src = part.strip().split()[0]
            if src:
                urls.add(urljoin(page_url, src))
    # CSS background-image: url(...)
    for m in re.finditer(r'url\(["\']?([^"\')\s]+)["\']?\)', html_str):
        u = m.group(1)
        if any(u.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
            urls.add(urljoin(page_url, u))
    return urls


def rewrite_html_images(html_str, image_id_map, page_url):
    """HTML内の画像参照を localnet://img/{id} に書き換え。amp-img → img 変換も行う"""

    def replace_src(match):
        full = match.group(0)
        src = match.group(1)
        abs_url = urljoin(page_url, src)
        if abs_url in image_id_map:
            return full.replace(src, f'localnet://img/{image_id_map[abs_url]}')
        return full

    # amp-img → img 変換
    html_str = re.sub(r'<amp-img\b', '<img', html_str, flags=re.IGNORECASE)
    html_str = re.sub(r'</amp-img>', '</img>', html_str, flags=re.IGNORECASE)

    # src属性書き換え
    html_str = re.sub(r'src=["\']([^"\']+)["\']', replace_src, html_str)

    # srcset属性書き換え
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


class DatasetBuilder:
    def __init__(self, domain, log=None):
        self.domain = domain
        self._log = log or print
        self.cache_dir = os.path.join(CACHE_BASE, domain)
        os.makedirs(DATASETS_DIR, exist_ok=True)

    def _find_cached_file(self, url, base):
        """URLに対応するキャッシュファイルを探す（サイズバリエーション対応）"""
        parsed = urlparse(url)
        path = unquote(parsed.path).lstrip('/')
        candidates = [
            os.path.join(base, path),
            os.path.join(self.cache_dir, parsed.netloc, path),
        ]
        # Thumbサイズバリエーション（Thumb300↔Thumb500↔Thumb630↔ThumbH75等）
        thumb_sizes = ['Thumb300', 'Thumb500', 'Thumb630', 'Thumb250x2', 'ThumbH75']
        for ts in thumb_sizes:
            if ts in path:
                for alt in thumb_sizes:
                    if alt != ts:
                        alt_path = path.replace(ts, alt)
                        candidates.append(os.path.join(base, alt_path))
                        candidates.append(os.path.join(self.cache_dir, parsed.netloc, alt_path))
                break
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def build(self):
        output_path = os.path.join(DATASETS_DIR, f"{self.domain}.sqlite")
        base = os.path.join(self.cache_dir, self.domain)
        if not os.path.exists(base):
            base = self.cache_dir

        self._log(f"データセット構築開始: {self.domain}")

        conn = sqlite3.connect(output_path)
        cur = conn.cursor()

        # スキーマ
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                domain TEXT NOT NULL,
                title TEXT,
                content_text TEXT,
                content_html BLOB,
                mime TEXT,
                fetched_at TEXT
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                data BLOB NOT NULL,
                mime TEXT
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')

        cur.execute("DROP TABLE IF EXISTS pages_fts")
        cur.execute('''
            CREATE VIRTUAL TABLE pages_fts USING fts5(
                title, content_text,
                content='pages', content_rowid='id',
                tokenize='unicode61'
            )
        ''')

        cur.executescript('''
            DROP TRIGGER IF EXISTS pages_ai;
            DROP TRIGGER IF EXISTS pages_ad;
            DROP TRIGGER IF EXISTS pages_au;

            CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
                INSERT INTO pages_fts(rowid, title, content_text)
                VALUES (new.id, new.title, new.content_text);
            END;

            CREATE TRIGGER pages_ad AFTER DELETE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, title, content_text)
                VALUES ('delete', old.id, old.title, old.content_text);
            END;

            CREATE TRIGGER pages_au AFTER UPDATE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, title, content_text)
                VALUES ('delete', old.id, old.title, old.content_text);
                INSERT INTO pages_fts(rowid, title, content_text)
                VALUES (new.id, new.title, new.content_text);
            END;
        ''')

        cur.execute("DELETE FROM pages")
        cur.execute("DELETE FROM images")

        now = datetime.now(timezone.utc).isoformat()

        # Pass 1: HTMLファイル収集 & 画像URL抽出
        self._log("Pass 1: HTML収集 & 画像URL抽出...")
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

                page_url = f"https://{self.domain}/{quote(url_path, safe='/:@!$&()*+,;=-._~')}"
                img_urls = extract_image_urls(html_str, page_url)
                all_image_urls.update(img_urls)
                html_files.append((filepath, url_path, page_url, raw, html_str))

        self._log(f"  HTML: {len(html_files)} ファイル, 画像URL: {len(all_image_urls)} 件")

        # Pass 2: 画像をDBに格納
        self._log("Pass 2: 画像格納中...")
        image_id_map = {}  # url -> image id
        img_count = 0

        for img_url in all_image_urls:
            # キャッシュ内を探す
            cached = self._find_cached_file(img_url, base)
            if not cached:
                continue

            try:
                with open(cached, 'rb') as f:
                    img_data = f.read()
                if len(img_data) == 0:
                    continue
                img_mime = detect_mime_from_bytes(img_data)
                cur.execute(
                    'INSERT OR IGNORE INTO images (url, data, mime) VALUES (?,?,?)',
                    (img_url, img_data, img_mime)
                )
                if cur.lastrowid:
                    image_id_map[img_url] = cur.lastrowid
                else:
                    row = cur.execute('SELECT id FROM images WHERE url=?', (img_url,)).fetchone()
                    if row:
                        image_id_map[img_url] = row[0]
                img_count += 1
                if img_count % 50 == 0:
                    self._log(f"  {img_count} 画像処理済み...")
                    conn.commit()
            except Exception:
                continue

        conn.commit()
        self._log(f"  {img_count} 画像格納完了 ({len(image_id_map)} 件マッチ)")

        # Pass 3: HTML書き換え & ページ格納
        self._log("Pass 3: HTML書き換え & ページ格納...")
        page_count = 0

        for filepath, url_path, page_url, raw, html_str in html_files:
            title = extract_title(html_str)
            content_text = extract_text(html_str)

            # 画像参照を書き換え
            rewritten = rewrite_html_images(html_str, image_id_map, page_url)
            content_html = gzip.compress(rewritten.encode('utf-8'), compresslevel=6)

            cur.execute(
                'INSERT INTO pages (url, domain, title, content_text, content_html, mime, fetched_at) VALUES (?,?,?,?,?,?,?)',
                (page_url, self.domain, title, content_text, content_html, 'text/html', now)
            )
            page_count += 1
            if page_count % 100 == 0:
                self._log(f"  {page_count} ページ処理済み...")
                conn.commit()

        # メタデータ
        cur.execute("INSERT OR REPLACE INTO meta VALUES ('name', ?)", (self.domain,))
        cur.execute("INSERT OR REPLACE INTO meta VALUES ('source_url', ?)", (f"https://{self.domain}/",))
        cur.execute("INSERT OR REPLACE INTO meta VALUES ('created_at', ?)", (now,))
        cur.execute("INSERT OR REPLACE INTO meta VALUES ('page_count', ?)", (str(page_count),))
        cur.execute("INSERT OR REPLACE INTO meta VALUES ('image_count', ?)", (str(img_count),))

        conn.commit()

        self._log("データベース最適化中...")
        conn.execute("VACUUM")
        conn.close()

        file_size = os.path.getsize(output_path)
        self._log(f"\u2705 データセット完成: {page_count} ページ, {img_count} 画像, {file_size / 1024 / 1024:.1f} MB")
        return output_path

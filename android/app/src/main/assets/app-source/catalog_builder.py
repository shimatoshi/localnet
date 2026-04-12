"""CatalogBuilder — cacheからcatalog.json生成（SQLite不要）
新フォルダ構造: cache/domain/page_path/index.html + リソース"""

import os
import re
import json
import gzip as _gzip
import mimetypes
import threading
from urllib.parse import quote

from config import CACHE_BASE
from utils import detect_charset

try:
    import brotli as _brotli
    _BROTLI_OK = True
except ImportError:
    _BROTLI_OK = False


def _read_html_bytes(filepath, max_bytes=None):
    """index.html / .html.br / .html.gz を読み込む。必要なら解凍。"""
    if filepath.endswith('.br') and _BROTLI_OK:
        with open(filepath, 'rb') as f:
            data = _brotli.decompress(f.read())
        return data[:max_bytes] if max_bytes else data
    if filepath.endswith('.gz'):
        with _gzip.open(filepath, 'rb') as f:
            return f.read(max_bytes) if max_bytes else f.read()
    with open(filepath, 'rb') as f:
        return f.read(max_bytes) if max_bytes else f.read()


def _extract_title(filepath):
    try:
        head = _read_html_bytes(filepath, max_bytes=8192)
        charset = detect_charset(head) or 'utf-8'
        html = head.decode(charset, errors='replace')
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if m:
            return re.sub(r'<[^>]+>', '', m.group(1)).strip()
    except Exception:
        pass
    return ''


def _extract_images(filepath, domain, page_path, page_title=''):
    """HTMLからimg要素を抽出してリストで返す"""
    images = []
    try:
        data = _read_html_bytes(filepath)
        charset = detect_charset(data[:8192]) or 'utf-8'
        html = data.decode(charset, errors='replace')
        # 新フォーマット: page_pathがディレクトリ名、srcはファイル名のみ
        # 旧フォーマット: page_pathがファイルパス
        for m in re.finditer(
            r'<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*?>',
            html, re.IGNORECASE | re.DOTALL
        ):
            tag = m.group(0)
            src = m.group(1)
            if src.startswith('data:'):
                continue
            alt = ''
            alt_m = re.search(r'alt=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if alt_m:
                alt = alt_m.group(1).strip()
            if src.startswith('http://') or src.startswith('https://'):
                img_url = src
            elif page_path:
                img_url = f'/api/cache/{domain}/{page_path}/{src}'
            else:
                img_url = f'/api/cache/{domain}/_root/{src}'
            images.append({
                'src': img_url,
                'alt': alt,
                'page_path': page_path,
                'page_title': page_title,
                'page_url': f'https://{domain}/{quote(page_path, safe="/:@!$&()*+,;=-._~")}' if page_path else f'https://{domain}/',
            })
    except Exception:
        pass
    return images


def _is_html(filepath):
    # .html / .html.br / .html.gz
    base = filepath
    if base.endswith('.br') or base.endswith('.gz'):
        base = base[:-3]
    mime, _ = mimetypes.guess_type(base)
    if mime and 'html' in mime:
        return True
    try:
        head = _read_html_bytes(filepath, max_bytes=256).lower()
        return b'<html' in head or b'<!doctype' in head
    except Exception:
        return False


_INDEX_VARIANTS = ('index.html', 'index.html.br', 'index.html.gz')


def _find_index_file(dirpath):
    """ディレクトリ内の index.html / .br / .gz を探す"""
    for name in _INDEX_VARIANTS:
        p = os.path.join(dirpath, name)
        if os.path.isfile(p):
            return p
    return None


def _detect_format(cache_dir, domain):
    """新旧フォーマットを検出。新(page-per-folder)を優先"""
    # 新フォーマット: いずれかのサブディレクトリにindex.html{,.br,.gz}がある
    try:
        for entry in os.listdir(cache_dir):
            subdir = os.path.join(cache_dir, entry)
            if os.path.isdir(subdir) and _find_index_file(subdir):
                return 'new', cache_dir
    except FileNotFoundError:
        pass
    # 旧フォーマット: cache/domain/domain/ がある
    old_base = os.path.join(cache_dir, domain)
    if os.path.isdir(old_base):
        return 'old', old_base
    # どちらでもない場合はcache_dir自体を走査
    return 'unknown', cache_dir


def build_catalog(domain, log=None):
    _log = log or print
    cache_dir = os.path.join(CACHE_BASE, domain)

    fmt, base = _detect_format(cache_dir, domain)
    _log(f"フォーマット検出: {fmt}")

    catalog = []
    all_images = []

    if fmt == 'new':
        # 新フォーマット: 各サブディレクトリがページ
        for root, dirs, files in os.walk(cache_dir):
            filepath = _find_index_file(root)
            if not filepath:
                continue

            # cache_dirからの相対パス = ページディレクトリ名
            rel_dir = os.path.relpath(root, cache_dir).replace(os.sep, '/')
            # _root → トップページ（空パス）
            if rel_dir == '_root':
                page_path = ''
            else:
                page_path = rel_dir

            title = _extract_title(filepath)
            url = f'https://{domain}/{quote(page_path, safe="/:@!$&()*+,;=-._~")}' if page_path else f'https://{domain}/'

            catalog.append({
                'url': url,
                'title': title or page_path or domain,
                'path': page_path,
            })

            images = _extract_images(filepath, domain, page_path, title)
            all_images.extend(images)
    else:
        # 旧フォーマット: フラットなHTMLファイル
        for root, _, files in os.walk(base):
            for fname in files:
                filepath = os.path.join(root, fname)
                if not _is_html(filepath):
                    continue

                relpath = os.path.relpath(filepath, base).replace(os.sep, '/')
                # .br/.gz 拡張子をパスから除去
                if relpath.endswith('.br') or relpath.endswith('.gz'):
                    relpath = relpath[:-3]
                title = _extract_title(filepath)
                url = f'https://{domain}/{quote(relpath, safe="/:@!$&()*+,;=-._~")}'

                catalog.append({
                    'url': url,
                    'title': title or relpath,
                    'path': relpath,
                })

                images = _extract_images(filepath, domain, relpath, title)
                all_images.extend(images)

    catalog_path = os.path.join(cache_dir, 'catalog.json')
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False)

    images_path = os.path.join(cache_dir, 'images.json')
    with open(images_path, 'w', encoding='utf-8') as f:
        json.dump(all_images, f, ensure_ascii=False)

    _log(f"カタログ生成完了: {len(catalog)} ページ, {len(all_images)} 画像")
    return catalog_path


# --- キャッシュ付きカタログ読み込み ---

_catalog_cache = {}
_catalog_mtime = {}
_catalog_lock = threading.Lock()


def load_catalog(domain):
    path = os.path.join(CACHE_BASE, domain, 'catalog.json')
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    with _catalog_lock:
        if domain in _catalog_cache and _catalog_mtime.get(domain) == mtime:
            return _catalog_cache[domain]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with _catalog_lock:
            _catalog_cache[domain] = data
            _catalog_mtime[domain] = mtime
        return data
    except Exception:
        return None


def load_images(domain):
    path = os.path.join(CACHE_BASE, domain, 'images.json')
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cache_key = f'img_{domain}'
    with _catalog_lock:
        if cache_key in _catalog_cache and _catalog_mtime.get(cache_key) == mtime:
            return _catalog_cache[cache_key]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with _catalog_lock:
            _catalog_cache[cache_key] = data
            _catalog_mtime[cache_key] = mtime
        return data
    except Exception:
        return None


def search_images(query, limit=50):
    query_lower = query.lower()
    results = []
    if not os.path.isdir(CACHE_BASE):
        return results
    for name in sorted(os.listdir(CACHE_BASE)):
        if not os.path.isdir(os.path.join(CACHE_BASE, name)):
            continue
        images = load_images(name)
        if not images:
            continue
        for img in images:
            if query_lower in (img.get('alt') or '').lower() or query_lower in img.get('src', '').lower() or query_lower in img.get('page_path', '').lower() or query_lower in (img.get('page_title') or '').lower():
                results.append({**img, 'domain': name})
                if len(results) >= limit:
                    return results
    return results


def search_catalogs(query, limit=50):
    query_lower = query.lower()
    results = []
    if not os.path.isdir(CACHE_BASE):
        return results
    for name in sorted(os.listdir(CACHE_BASE)):
        if not os.path.isdir(os.path.join(CACHE_BASE, name)):
            continue
        catalog = load_catalog(name)
        if not catalog:
            continue
        for entry in catalog:
            if query_lower in entry['title'].lower() or query_lower in entry.get('path', '').lower():
                results.append({
                    'url': entry['url'],
                    'title': entry['title'],
                    'path': entry['path'],
                    'domain': name,
                })
                if len(results) >= limit:
                    return results
    return results

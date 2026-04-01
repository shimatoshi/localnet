"""CatalogBuilder — cacheからcatalog.json生成（SQLite不要）"""

import os
import re
import json
import mimetypes
import threading
from urllib.parse import quote

from config import CACHE_BASE


def _detect_charset(raw):
    """HTMLバイト列からcharsetを検出"""
    head = raw[:4096].lower()
    # <meta charset="...">
    m = re.search(rb'<meta\s[^>]*charset=["\']?([a-zA-Z0-9_-]+)', head)
    if m:
        return m.group(1).decode('ascii', errors='ignore')
    # <meta http-equiv="content-type" content="text/html; charset=...">
    m = re.search(rb'content-type[^>]*charset=([a-zA-Z0-9_-]+)', head)
    if m:
        return m.group(1).decode('ascii', errors='ignore')
    return None


def _extract_title(filepath):
    try:
        with open(filepath, 'rb') as f:
            head = f.read(8192)
        charset = _detect_charset(head) or 'utf-8'
        html = head.decode(charset, errors='replace')
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if m:
            return re.sub(r'<[^>]+>', '', m.group(1)).strip()
    except Exception:
        pass
    return ''


def _is_html(filepath):
    mime, _ = mimetypes.guess_type(filepath)
    if mime and 'html' in mime:
        return True
    try:
        with open(filepath, 'rb') as f:
            head = f.read(256).lower()
        return b'<html' in head or b'<!doctype' in head
    except Exception:
        return False


def build_catalog(domain, log=None):
    _log = log or print
    cache_dir = os.path.join(CACHE_BASE, domain)
    base = os.path.join(cache_dir, domain)
    if not os.path.isdir(base):
        base = cache_dir

    catalog = []
    for root, _, files in os.walk(base):
        for fname in files:
            filepath = os.path.join(root, fname)
            if not _is_html(filepath):
                continue

            relpath = os.path.relpath(filepath, base).replace(os.sep, '/')
            title = _extract_title(filepath)
            url = f'https://{domain}/{quote(relpath, safe="/:@!$&()*+,;=-._~")}'

            catalog.append({
                'url': url,
                'title': title or relpath,
                'path': relpath,
            })

    catalog_path = os.path.join(cache_dir, 'catalog.json')
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False)

    _log(f"カタログ生成完了: {len(catalog)} ページ")
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

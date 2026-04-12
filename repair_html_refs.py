#!/usr/bin/env python3
"""クロール済み index.html の絶対URL img/amp-img src を、
URL ハッシュから実ファイルを逆引きしてローカル相対パスに書き換える。

引数: <domain> (例: www.zukan-bouz.com)
"""

import os
import re
import sys
import hashlib
import gzip

try:
    import brotli
except ImportError:
    brotli = None

# 進捗をリアルタイム表示するため line buffering
sys.stdout.reconfigure(line_buffering=True)

_BROTLI_QUALITY = 6  # 11 は遅すぎ（1ファイル数秒）。6 でも圧縮率は十分


CACHE_BASE = '/data/data/net.localnet.app.dev/files/cache'
EXT_CANDIDATES = ('.webp', '.jpg', '.jpeg', '.png', '.gif', '.svg')


def url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()[:8]


def build_shared_index(shared_dir):
    """_shared/ の <origstem>_<hash>.<ext> から hash -> filename へ逆引き"""
    idx = {}
    if not os.path.isdir(shared_dir):
        return idx
    for f in os.listdir(shared_dir):
        stem, ext = os.path.splitext(f)
        if ext.lower() not in EXT_CANDIDATES:
            continue
        m = re.match(r'^(.+)_([0-9a-f]{8})$', stem)
        if m:
            h = m.group(2)
            idx.setdefault(h, f)
    return idx


def find_local_name(abs_url, page_dir, shared_index, domain):
    """abs_url に対応するローカル相対パス（または _shared へのフル絶対パス）"""
    h = url_hash(abs_url)
    basename = abs_url.rstrip('/').rsplit('/', 1)[-1]
    basename = basename.split('?', 1)[0].split('#', 1)[0]
    if not basename:
        return None
    stem, _ext = os.path.splitext(basename)
    safe_stem = re.sub(r'[<>:"|?*]', '_', stem)[:50]

    if os.path.isdir(page_dir):
        for ext in EXT_CANDIDATES:
            candidate = f'{safe_stem}_{h}{ext}'
            if os.path.isfile(os.path.join(page_dir, candidate)):
                return candidate  # 相対（page_dir内）

    if h in shared_index:
        return f'/api/cache/{domain}/_shared/{shared_index[h]}'

    return None


_IMG_RE = re.compile(
    r'(<(?:img|amp-img)\s[^>]*?src=")([^"]+)(")',
    re.IGNORECASE,
)


_AMP_IMG_OPEN = re.compile(r'<amp-img\b', re.IGNORECASE)
_AMP_IMG_CLOSE = re.compile(r'</amp-img\s*>', re.IGNORECASE)


def rewrite_html(html, page_dir, shared_index, domain):
    stats = {'rewrote': 0, 'unresolved': 0, 'amp_converted': 0}

    def repl(m):
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if src.startswith('data:'):
            return m.group(0)
        if src.startswith(f'https://{domain}') or src.startswith(f'http://{domain}'):
            abs_url = src
        elif src.startswith('/') and not src.startswith('//'):
            abs_url = f'https://{domain}{src}'
        else:
            return m.group(0)

        local = find_local_name(abs_url, page_dir, shared_index, domain)
        if local:
            stats['rewrote'] += 1
            return f'{prefix}{local}{suffix}'
        stats['unresolved'] += 1
        return m.group(0)

    new_html = _IMG_RE.sub(repl, html)

    # <amp-img> → <img> 変換（AMP runtime なしでも表示されるように）
    amp_count = len(_AMP_IMG_OPEN.findall(new_html))
    if amp_count:
        new_html = _AMP_IMG_OPEN.sub('<img', new_html)
        new_html = _AMP_IMG_CLOSE.sub('', new_html)
        stats['amp_converted'] = amp_count

    return new_html, stats


def process_file(filepath, page_dir, shared_index, domain):
    is_br = filepath.endswith('.br')
    is_gz = filepath.endswith('.gz')
    try:
        with open(filepath, 'rb') as f:
            raw = f.read()
        if is_br:
            if not brotli:
                return {'rewrote': 0, 'unresolved': 0}
            html_bytes = brotli.decompress(raw)
        elif is_gz:
            html_bytes = gzip.decompress(raw)
        else:
            html_bytes = raw
        html = html_bytes.decode('utf-8', errors='replace')
    except Exception as e:
        print(f"  読込失敗: {filepath}: {e}")
        return {'rewrote': 0, 'unresolved': 0}

    new_html, stats = rewrite_html(html, page_dir, shared_index, domain)
    # いずれかの変更があれば書き込み
    if stats['rewrote'] == 0 and stats.get('amp_converted', 0) == 0:
        return stats

    try:
        new_bytes = new_html.encode('utf-8')
        if is_br:
            out = brotli.compress(new_bytes, quality=_BROTLI_QUALITY)
        elif is_gz:
            out = gzip.compress(new_bytes, compresslevel=9)
        else:
            out = new_bytes
        with open(filepath, 'wb') as f:
            f.write(out)
    except Exception as e:
        print(f"  書込失敗: {filepath}: {e}")
    return stats


def main():
    if len(sys.argv) < 2:
        print("usage: repair_html_refs.py <domain>")
        sys.exit(1)
    domain = sys.argv[1]
    site_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(site_dir):
        print(f"no site: {site_dir}")
        sys.exit(1)

    shared_dir = os.path.join(site_dir, '_shared')
    shared_index = build_shared_index(shared_dir)
    print(f"_shared index: {len(shared_index)} entries")

    total = {'files_touched': 0, 'rewrote': 0, 'unresolved': 0, 'amp_converted': 0}
    processed = 0
    for root, dirs, files in os.walk(site_dir):
        if os.path.basename(root) == '_shared':
            dirs[:] = []
            continue
        for f in files:
            if f not in ('index.html', 'index.html.br', 'index.html.gz'):
                continue
            filepath = os.path.join(root, f)
            stats = process_file(filepath, root, shared_index, domain)
            if stats['rewrote'] or stats.get('amp_converted', 0):
                total['files_touched'] += 1
                total['rewrote'] += stats['rewrote']
                total['amp_converted'] += stats.get('amp_converted', 0)
            total['unresolved'] += stats['unresolved']
            processed += 1
            if processed % 200 == 0:
                print(f"進捗: {processed} ファイル処理")

    print(f"完了: {total['files_touched']} ファイル更新, "
          f"{total['rewrote']} 画像参照rewrite, "
          f"{total['amp_converted']} amp-img→img変換, "
          f"{total['unresolved']} 解決不能")


if __name__ == '__main__':
    main()

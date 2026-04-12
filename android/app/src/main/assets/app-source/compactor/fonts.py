"""フォント処理:
  deduplicate_fonts — 全フォントを _shared/fonts/ に集約、CSSの参照も書き換え
  strip_obsolete_formats — woff2以外のフォント形式を削除、CSSから該当 src エントリ除去
"""

import os
import re
import gzip
import shutil

from config import FONTS_BASE

# 対応フォント拡張子
FONT_EXTS = {'.woff2', '.woff', '.ttf', '.eot', '.svg', '.otf'}

# CSS 内のフォント URL 正規表現
_FONT_URL_RE = re.compile(
    r'url\((["\']?)([^)"\':]+\.(?:woff2|woff|ttf|eot|svg|otf))\1\)')

# 拡張子なしフォント検出用マジックバイト
_FONT_MAGIC = (
    b'\x00\x01\x00\x00',  # TrueType
    b'true',               # TrueType (Mac)
    b'OTTO',               # OpenType
    b'wOFF',               # WOFF
    b'wOF2',               # WOFF2
    b'\x01\x00\x00\x00',   # Some TTF variants
)

# woff2 以外の obsolete 形式
_OBSOLETE_FONT_EXTS = {'.woff', '.ttf', '.eot', '.otf'}
_OBSOLETE_FONT_SVG_PREFIXES = ('fa-', 'fontawesome')

# CSS @font-face src の woff2 以外の format() エントリ
_FONT_SRC_ENTRY = re.compile(
    r',?\s*url\([^)]+\)\s*format\(\s*["\'](?:embedded-opentype|woff|truetype|svg)["\']'
    r'\s*\)',
    re.IGNORECASE)
# 先頭の単独 url(xxx.eot) — format() なしの IE 用
_FONT_SRC_EOT_BARE = re.compile(
    r'src:\s*url\([^)]+\.eot[^)]*\)\s*;\s*', re.IGNORECASE)


def _is_font_by_magic(filepath):
    try:
        with open(filepath, 'rb') as f:
            head = f.read(4)
        return head in _FONT_MAGIC
    except Exception:
        return False


def _rewrite_font_urls(css_text, shared_fonts):
    def _replace(m):
        quote = m.group(1)
        filename = m.group(2)
        basename = filename.rsplit('/', 1)[-1] if '/' in filename else filename
        if basename in shared_fonts:
            return f'url({quote}/_shared/fonts/{basename}{quote})'
        return m.group(0)
    return _FONT_URL_RE.sub(_replace, css_text)


def _rewrite_css_fonts_in_dir(site_dir, shared_fonts, log):
    count = 0
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            if not f.endswith('.css'):
                continue
            css_path = os.path.join(root, f)
            try:
                with open(css_path, 'r', encoding='utf-8', errors='replace') as fh:
                    text = fh.read()
                new_text = _rewrite_font_urls(text, shared_fonts)
                if new_text != text:
                    with open(css_path, 'w', encoding='utf-8') as fh:
                        fh.write(new_text)
                    count += 1
            except Exception:
                pass
    if count:
        log(f"[compactor] CSS {count}件のフォント参照を書き換え")


def deduplicate_fonts(site_dir, log):
    """フォントを共有ディレクトリに集約し、CSS参照を書き換え、元ファイル削除"""
    os.makedirs(FONTS_BASE, exist_ok=True)
    stats = {'removed': 0, 'bytes_saved': 0}

    font_files = []
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in FONT_EXTS:
                font_files.append((os.path.join(root, f), f))

    if not font_files:
        log("[compactor] フォントファイルなし")
        return stats

    shared_fonts = set()
    for filepath, filename in font_files:
        shared_path = os.path.join(FONTS_BASE, filename)
        if not os.path.exists(shared_path):
            try:
                shutil.copy2(filepath, shared_path)
            except Exception:
                continue
        shared_fonts.add(filename)

    _rewrite_css_fonts_in_dir(site_dir, shared_fonts, log)

    for filepath, filename in font_files:
        if filename in shared_fonts:
            try:
                size = os.path.getsize(filepath)
                os.remove(filepath)
                stats['removed'] += 1
                stats['bytes_saved'] += size
            except Exception:
                pass

    log(f"[compactor] フォント: {stats['removed']}件削除 "
        f"({stats['bytes_saved'] / 1048576:.1f}MB), "
        f"共有: {len(shared_fonts)}件")
    return stats


def strip_obsolete_formats(site_dir, log):
    """woff2以外のフォントを削除し、CSS @font-face src から該当エントリ除去"""
    stats = {'removed': 0, 'bytes_saved': 0}

    # 1. 共有フォントディレクトリから woff2 以外削除
    if os.path.isdir(FONTS_BASE):
        for f in os.listdir(FONTS_BASE):
            ext = os.path.splitext(f)[1].lower()
            name = os.path.splitext(f)[0].lower()
            should_remove = (ext in _OBSOLETE_FONT_EXTS or
                             (ext == '.svg' and any(name.startswith(p)
                              for p in _OBSOLETE_FONT_SVG_PREFIXES)))
            if should_remove:
                fpath = os.path.join(FONTS_BASE, f)
                try:
                    size = os.path.getsize(fpath)
                    os.remove(fpath)
                    stats['removed'] += 1
                    stats['bytes_saved'] += size
                except Exception:
                    pass

    # 2. サイト内の残存フォント削除（拡張子なしもマジックバイトで検出）
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            name = os.path.splitext(f)[0].lower()
            fpath = os.path.join(root, f)
            is_obsolete = (ext in _OBSOLETE_FONT_EXTS or
                           (ext == '.svg' and any(name.startswith(p)
                            for p in _OBSOLETE_FONT_SVG_PREFIXES)) or
                           (not ext and _is_font_by_magic(fpath)))
            if is_obsolete:
                try:
                    size = os.path.getsize(fpath)
                    os.remove(fpath)
                    stats['removed'] += 1
                    stats['bytes_saved'] += size
                except Exception:
                    pass

    # 3. CSS の @font-face src から不要フォーマット除去
    css_count = 0
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            if not f.endswith('.css') and not f.endswith('.css.gz'):
                continue
            fpath = os.path.join(root, f)
            try:
                if f.endswith('.gz'):
                    with gzip.open(fpath, 'rt', encoding='utf-8', errors='replace') as fh:
                        text = fh.read()
                else:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
                        text = fh.read()

                new_text = _FONT_SRC_EOT_BARE.sub('', text)
                new_text = _FONT_SRC_ENTRY.sub('', new_text)
                new_text = re.sub(r'src:\s*,\s*', 'src:', new_text)

                if new_text != text:
                    if f.endswith('.gz'):
                        with gzip.open(fpath, 'wt', encoding='utf-8') as fh:
                            fh.write(new_text)
                    else:
                        with open(fpath, 'w', encoding='utf-8') as fh:
                            fh.write(new_text)
                    css_count += 1
            except Exception:
                pass

    log(f"[compactor] フォント形式最適化: {stats['removed']}件削除 "
        f"({stats['bytes_saved'] / 1048576:.1f}MB), CSS {css_count}件書き換え")
    return stats

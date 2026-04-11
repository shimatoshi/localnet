"""compactor.py — キャッシュ圧縮モジュール
フォント重複排除・画像webp変換・不要ファイル削除を行う。
クローラーの自動圧縮パス / API手動実行の両方から利用。"""

import os
import re
import gzip
import shutil
import subprocess
from config import CACHE_BASE, FONTS_BASE

# webp変換: cwebp優先、なければPillow
_USE_CWEBP = False
_USE_PILLOW = False

try:
    subprocess.run(['cwebp', '-version'], capture_output=True, check=True)
    _USE_CWEBP = True
except Exception:
    try:
        # Android: PILの.soが依存するライブラリを事前にロード
        import ctypes, sys
        _bundle_lib = os.path.join(os.environ.get('PYTHONHOME', ''), 'lib')
        _preload_errors = []
        if os.path.isdir(_bundle_lib):
            for _lib in ['libzstd.so.1', 'libsharpyuv.so', 'libjpeg.so.8',
                         'libopenjp2.so', 'libtiff.so', 'libpng16.so',
                         'libXau.so', 'libXdmcp.so', 'libxcb.so',
                         'libwebp.so', 'libwebpmux.so', 'libwebpdemux.so']:
                _p = os.path.join(_bundle_lib, _lib)
                if os.path.exists(_p):
                    try:
                        ctypes.CDLL(_p, mode=ctypes.RTLD_GLOBAL)
                    except Exception as _e:
                        _preload_errors.append(f"{_lib}: {_e}")
        if _preload_errors:
            _err_path = os.path.join(os.path.dirname(__file__), 'preload_errors.txt')
            with open(_err_path, 'w') as _f:
                _f.write('\n'.join(_preload_errors))
        from PIL import Image
        _USE_PILLOW = True
    except Exception as _e:
        _err_path = os.path.join(os.path.dirname(__file__), 'pil_error.txt')
        with open(_err_path, 'w') as _f:
            import traceback
            traceback.print_exc(file=_f)

# フォント拡張子
FONT_EXTS = {'.woff2', '.woff', '.ttf', '.eot', '.svg', '.otf'}
# 画像拡張子（webp変換対象）
IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}
# フォントURL正規表現（CSS内）
_FONT_URL_RE = re.compile(
    r'url\((["\']?)([^)"\':]+\.(?:woff2|woff|ttf|eot|svg|otf))\1\)')


def compact_site(domain, log=None):
    """指定ドメインのキャッシュを圧縮。
    Returns: dict with stats (fonts_removed, images_converted, bytes_saved)
    """
    log = log or print
    site_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(site_dir):
        log(f"[compactor] {domain}: ディレクトリなし、スキップ")
        return {'fonts_removed': 0, 'images_converted': 0, 'bytes_saved': 0}

    stats = {'fonts_removed': 0, 'images_converted': 0, 'bytes_saved': 0}

    # Phase 1: フォント重複排除
    log(f"[compactor] {domain}: フォント重複排除開始")
    f_stats = _deduplicate_fonts(site_dir, log)
    stats['fonts_removed'] = f_stats['removed']
    stats['bytes_saved'] += f_stats['bytes_saved']

    # Phase 2: 画像webp変換
    log(f"[compactor] {domain}: 画像webp変換開始")
    i_stats = _convert_images_to_webp(site_dir, log)
    stats['images_converted'] = i_stats['converted']
    stats['bytes_saved'] += i_stats['bytes_saved']

    # Phase 2.5: 不要フォント形式削除（woff2のみ残す）
    log(f"[compactor] {domain}: フォント形式最適化開始")
    s_stats = _strip_font_formats(site_dir, log)
    stats['fonts_stripped'] = s_stats['removed']
    stats['bytes_saved'] += s_stats['bytes_saved']

    # Phase 3: 汎用リソース重複排除（CSS, 画像, その他）
    log(f"[compactor] {domain}: リソース重複排除開始")
    d_stats = _deduplicate_resources(site_dir, log)
    stats['deduped'] = d_stats['removed']
    stats['bytes_saved'] += d_stats['bytes_saved']

    # Phase 4: テキストファイルgzip圧縮
    log(f"[compactor] {domain}: gzip圧縮開始")
    g_stats = _gzip_text_files(site_dir, log)
    stats['gzipped'] = g_stats['compressed']
    stats['bytes_saved'] += g_stats['bytes_saved']

    log(f"[compactor] {domain}: 完了 — "
        f"フォント{stats['fonts_removed']}件削除, "
        f"画像{stats['images_converted']}件変換, "
        f"重複{stats.get('deduped', 0)}件排除, "
        f"gzip{stats.get('gzipped', 0)}件, "
        f"{stats['bytes_saved'] / 1048576:.1f}MB節約")
    return stats


def _deduplicate_fonts(site_dir, log):
    """フォントファイルを共有ディレクトリに集約し、CSS参照を書き換え、元ファイル削除"""
    os.makedirs(FONTS_BASE, exist_ok=True)
    stats = {'removed': 0, 'bytes_saved': 0}

    # 全フォントファイルを収集
    font_files = []  # (filepath, filename)
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in FONT_EXTS:
                font_files.append((os.path.join(root, f), f))

    if not font_files:
        log(f"[compactor] フォントファイルなし")
        return stats

    # ユニークフォントを共有ディレクトリにコピー
    shared_fonts = set()
    for filepath, filename in font_files:
        shared_path = os.path.join(FONTS_BASE, filename)
        if not os.path.exists(shared_path):
            try:
                shutil.copy2(filepath, shared_path)
            except Exception:
                continue
        shared_fonts.add(filename)

    # CSS内のフォント参照を共有パスに書き換え
    _rewrite_css_fonts_in_dir(site_dir, shared_fonts, log)

    # 元のフォントファイルを削除
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


# woff2以外のフォント拡張子
_OBSOLETE_FONT_EXTS = {'.woff', '.ttf', '.eot', '.otf'}
# SVGフォントも不要だがアイコンSVGと区別が必要
# fa-*, fontawesome-* のSVGのみ削除対象
_OBSOLETE_FONT_SVG_PREFIXES = ('fa-', 'fontawesome')
# @font-faceのsrc内でwoff2以外のformat()エントリを除去する正規表現
# "url(...) format("embedded-opentype")," のようなエントリを消す
_FONT_SRC_ENTRY = re.compile(
    r',?\s*url\([^)]+\)\s*format\(\s*["\'](?:embedded-opentype|woff|truetype|svg)["\']'
    r'\s*\)',
    re.IGNORECASE)
# 先頭の単独url(xxx.eot) — format()なしのIE用
_FONT_SRC_EOT_BARE = re.compile(
    r'src:\s*url\([^)]+\.eot[^)]*\)\s*;\s*', re.IGNORECASE)


def _strip_font_formats(site_dir, log):
    """woff2以外のフォントファイルを共有ディレクトリから削除し、
    CSSの@font-face srcからも不要エントリを除去"""
    stats = {'removed': 0, 'bytes_saved': 0}

    # 1. 共有フォントディレクトリからwoff2以外を削除
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

    # 2. サイト内に残っているwoff/ttf/eot/SVGフォントも削除
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            name = os.path.splitext(f)[0].lower()
            is_obsolete = (ext in _OBSOLETE_FONT_EXTS or
                           (ext == '.svg' and any(name.startswith(p)
                            for p in _OBSOLETE_FONT_SVG_PREFIXES)))
            if is_obsolete:
                fpath = os.path.join(root, f)
                try:
                    size = os.path.getsize(fpath)
                    os.remove(fpath)
                    stats['removed'] += 1
                    stats['bytes_saved'] += size
                except Exception:
                    pass

    # 3. CSS内の@font-face srcから不要フォーマットを除去
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
                # 先頭カンマの掃除: src: , url(...) -> src: url(...)
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


def _rewrite_css_fonts_in_dir(site_dir, shared_fonts, log):
    """ディレクトリ内の全CSSファイルのフォントURLを共有パスに書き換え"""
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


def _rewrite_font_urls(css_text, shared_fonts):
    """CSS内のフォントURLを共有パスに書き換え"""
    def _replace(m):
        quote = m.group(1)
        filename = m.group(2)
        basename = filename.rsplit('/', 1)[-1] if '/' in filename else filename
        if basename in shared_fonts:
            return f'url({quote}/_shared/fonts/{basename}{quote})'
        return m.group(0)
    return _FONT_URL_RE.sub(_replace, css_text)


# 各ページ固有のファイルは共有化しない（gz版も含む）
_SKIP_SHARED = {'index.html', 'index.html.gz', 'catalog.json', 'images.json'}

def _deduplicate_resources(site_dir, log):
    """同名ファイル（=同一コンテンツ）を _shared/ に集約して重複削除。
    サーバー側フォールバックでHTMLの参照変更不要。"""
    shared_dir = os.path.join(site_dir, '_shared')
    os.makedirs(shared_dir, exist_ok=True)
    stats = {'removed': 0, 'bytes_saved': 0}

    # ファイル名 → 出現リスト を収集
    file_map = {}  # filename -> [filepath, ...]
    for root, dirs, files in os.walk(site_dir):
        # _shared自身はスキップ
        if os.path.realpath(root).startswith(os.path.realpath(shared_dir)):
            continue
        for f in files:
            if f in _SKIP_SHARED:
                continue
            file_map.setdefault(f, []).append(os.path.join(root, f))

    # 2回以上出現するファイルを共有化
    dedup_count = 0
    for filename, paths in file_map.items():
        if len(paths) < 2:
            continue

        shared_path = os.path.join(shared_dir, filename)
        # 共有ディレクトリにまだなければ1つ目をコピー
        if not os.path.exists(shared_path):
            try:
                shutil.copy2(paths[0], shared_path)
            except Exception:
                continue

        # 全コピーを削除（共有から配信される）
        for p in paths:
            try:
                size = os.path.getsize(p)
                os.remove(p)
                stats['removed'] += 1
                stats['bytes_saved'] += size
            except Exception:
                pass
        dedup_count += 1

    if dedup_count:
        shared_count = len(os.listdir(shared_dir))
        log(f"[compactor] リソース重複排除: {stats['removed']}件削除 "
            f"({stats['bytes_saved'] / 1048576:.1f}MB), "
            f"共有: {shared_count}件")
    else:
        log(f"[compactor] 重複リソースなし")
    return stats


def _convert_one(src_path, dst_path):
    """1ファイルをwebpに変換。成功でTrue"""
    if _USE_CWEBP:
        result = subprocess.run(
            ['cwebp', '-q', '80', '-quiet', src_path, '-o', dst_path],
            capture_output=True, timeout=10)
        return result.returncode == 0
    elif _USE_PILLOW:
        from PIL import Image
        try:
            img = Image.open(src_path)
            img.save(dst_path, 'WEBP', quality=80)
            return True
        except Exception:
            return False
    return False


def _convert_images_to_webp(site_dir, log):
    """jpg/pngをwebpに変換し、HTML/CSS内の参照を書き換え"""
    stats = {'converted': 0, 'bytes_saved': 0}

    if not _USE_CWEBP and not _USE_PILLOW:
        log("[compactor] cwebp/Pillow未インストール、画像変換スキップ")
        return stats

    # 全画像ファイルを収集
    image_files = []  # (filepath, filename)
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTS:
                image_files.append((os.path.join(root, f), f))

    if not image_files:
        log("[compactor] 変換対象画像なし")
        return stats

    log(f"[compactor] 画像 {len(image_files)}件を変換中...")

    # ファイル名→webpファイル名のマッピング（HTML書き換え用）
    rename_map = {}  # old_filename -> new_filename
    converted_dirs = set()

    for i, (filepath, filename) in enumerate(image_files):
        name, ext = os.path.splitext(filename)
        webp_name = name + '.webp'
        webp_path = os.path.join(os.path.dirname(filepath), webp_name)

        # 既にwebpが存在する場合スキップ
        if os.path.exists(webp_path):
            # 元ファイルがまだあれば削除だけ
            try:
                old_size = os.path.getsize(filepath)
                os.remove(filepath)
                stats['bytes_saved'] += old_size
                stats['converted'] += 1
                rename_map[filename] = webp_name
                converted_dirs.add(os.path.dirname(filepath))
            except Exception:
                pass
            continue

        try:
            old_size = os.path.getsize(filepath)
            ok = _convert_one(filepath, webp_path)

            if ok and os.path.exists(webp_path):
                new_size = os.path.getsize(webp_path)
                # webpの方が大きい場合は変換取り消し
                if new_size >= old_size:
                    os.remove(webp_path)
                    continue
                os.remove(filepath)
                stats['converted'] += 1
                stats['bytes_saved'] += old_size - new_size
                rename_map[filename] = webp_name
                converted_dirs.add(os.path.dirname(filepath))
            else:
                if os.path.exists(webp_path):
                    os.remove(webp_path)
        except Exception:
            if os.path.exists(webp_path):
                try:
                    os.remove(webp_path)
                except Exception:
                    pass

        if (i + 1) % 500 == 0:
            log(f"[compactor] 画像変換進捗: {i + 1}/{len(image_files)}")

    # HTML/CSS内の画像参照を書き換え
    if rename_map:
        _rewrite_image_refs(site_dir, rename_map, converted_dirs, log)

    log(f"[compactor] 画像: {stats['converted']}件変換 "
        f"({stats['bytes_saved'] / 1048576:.1f}MB節約)")
    return stats


def _rewrite_image_refs(site_dir, rename_map, converted_dirs, log):
    """HTML/CSS内の画像ファイル名参照を書き換え"""
    # 変換があったディレクトリ内のHTML/CSSのみ対象（効率化）
    count = 0
    for dir_path in converted_dirs:
        for f in os.listdir(dir_path):
            if not f.endswith(('.html', '.css')):
                continue
            filepath = os.path.join(dir_path, f)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
                    text = fh.read()
                new_text = text
                for old_name, new_name in rename_map.items():
                    if old_name in new_text:
                        new_text = new_text.replace(old_name, new_name)
                if new_text != text:
                    with open(filepath, 'w', encoding='utf-8') as fh:
                        fh.write(new_text)
                    count += 1
            except Exception:
                pass
    if count:
        log(f"[compactor] HTML/CSS {count}件の画像参照を書き換え")


# gzip圧縮対象
_GZIP_EXTS = {'.html', '.css'}
_GZIP_MIN_SIZE = 512  # これ以下は圧縮しても効果薄い


def _gzip_text_files(site_dir, log):
    """HTML/CSSをgzip圧縮して.gz付きで保存、元ファイル削除。
    サーバー側で.gzファイルを検出して配信。"""
    stats = {'compressed': 0, 'bytes_saved': 0}

    targets = []
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in _GZIP_EXTS:
                continue
            filepath = os.path.join(root, f)
            # 既にgz化済みならスキップ
            if os.path.exists(filepath + '.gz'):
                continue
            targets.append(filepath)

    if not targets:
        log("[compactor] gzip対象なし")
        return stats

    log(f"[compactor] gzip圧縮: {len(targets)}件")

    for filepath in targets:
        try:
            with open(filepath, 'rb') as f:
                raw = f.read()
            if len(raw) < _GZIP_MIN_SIZE:
                continue
            compressed = gzip.compress(raw, compresslevel=9)
            # 圧縮効果が10%未満なら無視
            if len(compressed) >= len(raw) * 0.9:
                continue
            gz_path = filepath + '.gz'
            with open(gz_path, 'wb') as f:
                f.write(compressed)
            saved = len(raw) - len(compressed)
            os.remove(filepath)
            stats['compressed'] += 1
            stats['bytes_saved'] += saved
        except Exception:
            pass

    log(f"[compactor] gzip: {stats['compressed']}件圧縮 "
        f"({stats['bytes_saved'] / 1048576:.1f}MB節約)")
    return stats

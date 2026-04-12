"""画像 jpg/png → webp 変換。

cwebp を優先、なければ Pillow。
Android: Pillow の .so が依存する libwebp/libjpeg 等を ctypes で事前ロード。
"""

import os
import subprocess

IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}
_WEBP_QUALITY = 60  # 写真系は60でも見た目ほぼ変わらない

_USE_CWEBP = False
_USE_PILLOW = False

try:
    subprocess.run(['cwebp', '-version'], capture_output=True, check=True)
    _USE_CWEBP = True
except Exception:
    try:
        # Android: PIL の .so が依存するライブラリを事前ロード
        import ctypes
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
            _err_path = os.path.join(os.path.dirname(__file__), '..', 'preload_errors.txt')
            with open(_err_path, 'w') as _f:
                _f.write('\n'.join(_preload_errors))
        from PIL import Image as _PILImage  # noqa: F401
        _USE_PILLOW = True
    except Exception:
        _err_path = os.path.join(os.path.dirname(__file__), '..', 'pil_error.txt')
        try:
            with open(_err_path, 'w') as _f:
                import traceback
                traceback.print_exc(file=_f)
        except Exception:
            pass


def _convert_one(src_path, dst_path):
    if _USE_CWEBP:
        result = subprocess.run(
            ['cwebp', '-q', str(_WEBP_QUALITY), '-quiet', src_path, '-o', dst_path],
            capture_output=True, timeout=10)
        return result.returncode == 0
    if _USE_PILLOW:
        from PIL import Image
        try:
            img = Image.open(src_path)
            img.save(dst_path, 'WEBP', quality=_WEBP_QUALITY)
            return True
        except Exception:
            return False
    return False


def _rewrite_image_refs(site_dir, rename_map, converted_dirs, log):
    """HTML/CSS 内の画像ファイル名参照を書き換え（変換があったディレクトリのみ）"""
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


def convert_images_to_webp(site_dir, log):
    stats = {'converted': 0, 'bytes_saved': 0}

    if not _USE_CWEBP and not _USE_PILLOW:
        log("[compactor] cwebp/Pillow未インストール、画像変換スキップ")
        return stats

    image_files = []
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTS:
                image_files.append((os.path.join(root, f), f))

    if not image_files:
        log("[compactor] 変換対象画像なし")
        return stats

    log(f"[compactor] 画像 {len(image_files)}件を変換中...")

    rename_map = {}  # old_filename -> new_filename
    converted_dirs = set()

    for i, (filepath, filename) in enumerate(image_files):
        name, ext = os.path.splitext(filename)
        webp_name = name + '.webp'
        webp_path = os.path.join(os.path.dirname(filepath), webp_name)

        # 既に webp 済みなら元ファイル削除だけ
        if os.path.exists(webp_path):
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
                # webp の方が大きい場合は取り消し
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

    if rename_map:
        _rewrite_image_refs(site_dir, rename_map, converted_dirs, log)

    log(f"[compactor] 画像: {stats['converted']}件変換 "
        f"({stats['bytes_saved'] / 1048576:.1f}MB節約)")
    return stats

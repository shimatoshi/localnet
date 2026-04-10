"""画像圧縮 — PNG/JPGをWebPに変換してHTML参照も書き換え"""

import os
import re
from config import CACHE_BASE

try:
    from PIL import Image
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False

# 変換対象の拡張子
_CONVERT_EXT = {'.png', '.jpg', '.jpeg'}
# WebP品質（0-100）
_WEBP_QUALITY = 80


def is_available():
    return _HAS_PILLOW


_MIN_SIZE = 10 * 1024  # 10KB未満はスキップ（WebP化で逆に増える）


def _convert_image(filepath):
    """画像をWebPに変換。小さくなった場合のみ採用。成功したらwebpパスを返す"""
    orig_size = os.path.getsize(filepath)
    if orig_size < _MIN_SIZE:
        return None
    try:
        with Image.open(filepath) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            webp_path = os.path.splitext(filepath)[0] + '.webp'
            img.save(webp_path, 'WEBP', quality=_WEBP_QUALITY)
        # WebPの方が大きければロールバック
        new_size = os.path.getsize(webp_path)
        if new_size >= orig_size:
            os.remove(webp_path)
            return None
        # 元ファイル削除
        os.remove(filepath)
        return webp_path
    except Exception:
        # 変換失敗時にWebPが残ってたら消す
        webp_path = os.path.splitext(filepath)[0] + '.webp'
        if os.path.exists(webp_path) and os.path.exists(filepath):
            os.remove(webp_path)
        return None


def _update_html_refs(html_path, old_name, new_name):
    """HTML内の画像参照をold_name→new_nameに書き換え"""
    try:
        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        new_content = content.replace(old_name, new_name)
        if new_content != content:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
    except Exception:
        pass
    return False


def compress_site(domain, log=None):
    """サイトの画像をWebPに変換し、HTML参照を更新"""
    _log = log or print

    if not _HAS_PILLOW:
        _log("エラー: Pillowが必要です (pip install Pillow)")
        return

    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        _log(f"キャッシュなし: {domain}")
        return

    # 変換対象の画像を収集
    images = []
    for root, dirs, files in os.walk(cache_dir):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _CONVERT_EXT:
                images.append((root, fname))

    if not images:
        _log("変換対象の画像なし")
        return

    # 元のサイズ計算
    total_before = sum(os.path.getsize(os.path.join(r, f)) for r, f in images)
    _log(f"変換対象: {len(images)} 画像 ({total_before / 1024 / 1024:.1f} MB)")

    converted = 0
    skipped = 0
    total_after = 0

    for i, (root, fname) in enumerate(images):
        filepath = os.path.join(root, fname)
        old_name = fname
        new_name = os.path.splitext(fname)[0] + '.webp'

        result = _convert_image(filepath)
        if result:
            new_size = os.path.getsize(result)
            total_after += new_size

            # 同じディレクトリのindex.htmlを更新
            index_path = os.path.join(root, 'index.html')
            if os.path.exists(index_path):
                _update_html_refs(index_path, old_name, new_name)

            converted += 1
        else:
            # 変換不要（小さい or WebPの方が大きい）
            if os.path.exists(filepath):
                total_after += os.path.getsize(filepath)
            skipped += 1

        if (i + 1) % 100 == 0:
            _log(f"  進捗: {i + 1}/{len(images)}")

    saved = total_before - total_after
    _log(f"完了: {converted} 変換, {skipped} スキップ")
    _log(f"削減: {total_before / 1024 / 1024:.1f} MB → {total_after / 1024 / 1024:.1f} MB ({saved / 1024 / 1024:.1f} MB 削減)")

"""compact_site — サイト圧縮の全体フロー。"""

import os

from config import CACHE_BASE

from .fonts import deduplicate_fonts, strip_obsolete_formats
from .images import convert_images_to_webp
from .dedup import deduplicate_resources
from .junk import remove_junk_files
from .minify import minify_text_files
from .compress import compress_text_files


def compact_site(domain, log=None):
    """指定ドメインのキャッシュを圧縮。

    Returns: dict with stats (fonts_removed, images_converted, bytes_saved, ...)
    """
    log = log or print
    site_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(site_dir):
        log(f"[compactor] {domain}: ディレクトリなし、スキップ")
        return {'fonts_removed': 0, 'images_converted': 0, 'bytes_saved': 0}

    stats = {'fonts_removed': 0, 'images_converted': 0, 'bytes_saved': 0}

    # Phase 1: フォント重複排除
    log(f"[compactor] {domain}: フォント重複排除開始")
    f_stats = deduplicate_fonts(site_dir, log)
    stats['fonts_removed'] = f_stats['removed']
    stats['bytes_saved'] += f_stats['bytes_saved']

    # Phase 2: 画像 webp 変換
    log(f"[compactor] {domain}: 画像webp変換開始")
    i_stats = convert_images_to_webp(site_dir, log)
    stats['images_converted'] = i_stats['converted']
    stats['bytes_saved'] += i_stats['bytes_saved']

    # Phase 2.5: 不要フォント形式削除（woff2 のみ残す）
    log(f"[compactor] {domain}: フォント形式最適化開始")
    s_stats = strip_obsolete_formats(site_dir, log)
    stats['fonts_stripped'] = s_stats['removed']
    stats['bytes_saved'] += s_stats['bytes_saved']

    # Phase 3: 汎用リソース重複排除
    log(f"[compactor] {domain}: リソース重複排除開始")
    d_stats = deduplicate_resources(site_dir, log)
    stats['deduped'] = d_stats['removed']
    stats['bytes_saved'] += d_stats['bytes_saved']

    # Phase 4: 不要ファイル削除
    log(f"[compactor] {domain}: 不要ファイル削除開始")
    j_stats = remove_junk_files(site_dir, log)
    stats['junk_removed'] = j_stats['removed']
    stats['bytes_saved'] += j_stats['bytes_saved']

    # Phase 5: HTML/CSS/SVG minify
    log(f"[compactor] {domain}: minify開始")
    m_stats = minify_text_files(site_dir, log)
    stats['minified'] = m_stats['minified']
    stats['bytes_saved'] += m_stats['bytes_saved']

    # Phase 6: brotli/gzip 圧縮
    log(f"[compactor] {domain}: gzip圧縮開始")
    g_stats = compress_text_files(site_dir, log)
    stats['gzipped'] = g_stats['compressed']
    stats['bytes_saved'] += g_stats['bytes_saved']

    log(f"[compactor] {domain}: 完了 — "
        f"フォント{stats['fonts_removed']}件削除, "
        f"画像{stats['images_converted']}件変換, "
        f"重複{stats.get('deduped', 0)}件排除, "
        f"不要{stats.get('junk_removed', 0)}件削除, "
        f"minify{stats.get('minified', 0)}件, "
        f"gzip{stats.get('gzipped', 0)}件, "
        f"{stats['bytes_saved'] / 1048576:.1f}MB節約")
    return stats

"""不要ファイル削除 — オフライン閲覧に無関係な favicon/sitemap/sourcemap 等。"""

import os

# オフライン閲覧に不要なファイル名パターン
_JUNK_BASENAMES = {
    'robots.txt', 'sitemap.xml', 'humans.txt', 'security.txt',
    'browserconfig.xml', 'crossdomain.xml', 'manifest.json',
    'site.webmanifest', '.DS_Store', 'Thumbs.db',
}
# 拡張子で判定する不要ファイル
_JUNK_EXTS = {'.map', '.ico'}  # source map, favicon
# ファイル名プレフィックス（ハッシュ付きファイル名に対応）
_JUNK_PREFIXES = (
    'favicon', 'apple-touch-icon', 'apple-icon', 'android-chrome',
    'mstile-', 'safari-pinned-tab',
)


def remove_junk_files(site_dir, log):
    stats = {'removed': 0, 'bytes_saved': 0}
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            fl = f.lower()
            is_junk = (
                fl in _JUNK_BASENAMES
                or ext in _JUNK_EXTS
                or any(fl.startswith(p) for p in _JUNK_PREFIXES)
            )
            if is_junk:
                fpath = os.path.join(root, f)
                try:
                    size = os.path.getsize(fpath)
                    os.remove(fpath)
                    stats['removed'] += 1
                    stats['bytes_saved'] += size
                except Exception:
                    pass
    if stats['removed']:
        log(f"[compactor] 不要ファイル: {stats['removed']}件削除 "
            f"({stats['bytes_saved'] / 1024:.1f}KB)")
    else:
        log("[compactor] 不要ファイルなし")
    return stats

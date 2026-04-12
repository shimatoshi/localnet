"""brotli / gzip 圧縮 — HTML/CSS/SVG を .br/.gz 付きで保存。

brotli が使えれば brotli 優先、なければ gzip。
"""

import os
import gzip

_TARGET_EXTS = {'.html', '.css', '.svg'}
_MIN_SIZE = 512  # これ以下は圧縮しても効果薄い

try:
    import brotli as _brotli
    _USE_BROTLI = True
except ImportError:
    _USE_BROTLI = False


def compress_text_files(site_dir, log):
    stats = {'compressed': 0, 'bytes_saved': 0}
    method = 'brotli' if _USE_BROTLI else 'gzip'

    targets = []
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in _TARGET_EXTS:
                continue
            filepath = os.path.join(root, f)
            # 既に.brまたは.gz化済みならスキップ
            if os.path.exists(filepath + '.br') or os.path.exists(filepath + '.gz'):
                continue
            targets.append(filepath)

    if not targets:
        log(f"[compactor] {method}対象なし")
        return stats

    log(f"[compactor] {method}圧縮: {len(targets)}件")

    for filepath in targets:
        try:
            with open(filepath, 'rb') as f:
                raw = f.read()
            if len(raw) < _MIN_SIZE:
                continue
            if _USE_BROTLI:
                compressed = _brotli.compress(raw, quality=11)
                ext_out = '.br'
            else:
                compressed = gzip.compress(raw, compresslevel=9)
                ext_out = '.gz'
            # 圧縮効果が10%未満なら無視
            if len(compressed) >= len(raw) * 0.9:
                continue
            out_path = filepath + ext_out
            with open(out_path, 'wb') as f:
                f.write(compressed)
            saved = len(raw) - len(compressed)
            os.remove(filepath)
            stats['compressed'] += 1
            stats['bytes_saved'] += saved
        except Exception:
            pass

    log(f"[compactor] {method}: {stats['compressed']}件圧縮 "
        f"({stats['bytes_saved'] / 1048576:.1f}MB節約)")
    return stats

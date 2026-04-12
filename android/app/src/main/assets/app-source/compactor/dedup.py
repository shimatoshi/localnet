"""同名＋同一ハッシュのファイルを _shared/ に集約して重複排除。

同名でも中身が違えば共有化しない（ハッシュで確認）。
"""

import os
import shutil
import hashlib


def _file_hash(filepath, chunk_size=8192):
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def deduplicate_resources(site_dir, log):
    shared_dir = os.path.join(site_dir, '_shared')
    os.makedirs(shared_dir, exist_ok=True)
    stats = {'removed': 0, 'bytes_saved': 0}

    # ファイル名 → 出現リスト を収集
    file_map = {}  # filename -> [filepath, ...]
    shared_realpath = os.path.realpath(shared_dir)
    for root, dirs, files in os.walk(site_dir):
        if os.path.realpath(root).startswith(shared_realpath):
            continue
        for f in files:
            file_map.setdefault(f, []).append(os.path.join(root, f))

    dedup_count = 0
    for filename, paths in file_map.items():
        if len(paths) < 2:
            continue

        # ハッシュでグループ化（同名・同ハッシュだけ共有化）
        hash_groups = {}
        for p in paths:
            try:
                h = _file_hash(p)
                hash_groups.setdefault(h, []).append(p)
            except Exception:
                pass

        for h, group in hash_groups.items():
            if len(group) < 2:
                continue

            shared_path = os.path.join(shared_dir, filename)
            if not os.path.exists(shared_path):
                try:
                    shutil.copy2(group[0], shared_path)
                except Exception:
                    continue

            for p in group:
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

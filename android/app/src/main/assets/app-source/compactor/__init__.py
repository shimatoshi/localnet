"""compactor パッケージ — キャッシュ圧縮モジュール

役割別に複数ファイルに分割:
  fonts.py    — フォント重複排除・形式最適化
  dedup.py    — ハッシュベース重複排除
  images.py   — jpg/png → webp 変換
  junk.py     — 不要ファイル削除
  minify.py   — html/css/svg minify
  compress.py — brotli/gzip 圧縮
  orchestrator.py — 全体フロー

利用側は `from compactor import compact_site` のみ。
"""

from .orchestrator import compact_site

__all__ = ['compact_site']

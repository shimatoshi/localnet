#!/bin/bash
# localnet 配布パッケージ作成
# cache/datasets/test/gitを除外して localnet.tar.gz を生成

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERSION=$(date +%Y%m%d)
OUTFILE="localnet-${VERSION}.tar.gz"

echo "=== localnet 配布パッケージ作成 ==="

tar czf "$OUTFILE" \
  --transform 's,^\./,localnet/,' \
  --exclude='./cache' \
  --exclude='./datasets' \
  --exclude='./.git' \
  --exclude='./.claude' \
  --exclude='./test_*.py' \
  --exclude='./*.tar' \
  --exclude='./*.tar.gz' \
  --exclude='./localnet-*.tar.gz' \
  --exclude='./build_dist.sh' \
  --exclude='./connect_pixel5.sh' \
  --exclude='./install_rclone.py' \
  --exclude='./upload_gofile.py' \
  --exclude='./upload_to_storage.py' \
  --exclude='./__pycache__' \
  .

SIZE=$(ls -lh "$OUTFILE" | awk '{print $5}')
echo ""
echo "完成: $OUTFILE ($SIZE)"
echo ""

# 内容確認
echo "=== 内容 ==="
tar tzf "$OUTFILE"

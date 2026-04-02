#!/bin/bash
# localnet セットアップスクリプト
# Termux (Android) / Linux 対応

set -e

echo "=== localnet セットアップ ==="
echo ""

# Termux判定
IS_TERMUX=false
if [ -d /data/data/com.termux ]; then
  IS_TERMUX=true
  echo "[環境] Termux (Android)"
else
  echo "[環境] Linux"
fi

# パッケージマネージャ判定
install_pkg() {
  if $IS_TERMUX; then
    pkg install -y "$@"
  elif command -v apt-get &>/dev/null; then
    sudo apt-get install -y "$@"
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y "$@"
  elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm "$@"
  else
    echo "エラー: パッケージマネージャが見つかりません"
    echo "手動で以下をインストールしてください: $*"
    exit 1
  fi
}

# 1. Python
echo ""
echo "[1/4] Python 確認..."
if command -v python3 &>/dev/null; then
  echo "  OK: $(python3 --version)"
else
  echo "  Python3をインストール中..."
  install_pkg python
fi

# 2. pip
echo ""
echo "[2/4] pip 確認..."
if python3 -m pip --version &>/dev/null 2>&1; then
  echo "  OK: $(python3 -m pip --version)"
else
  echo "  pipが見つかりません。インストール中..."
  if $IS_TERMUX; then
    pkg install -y python-pip
  else
    install_pkg python3-pip
  fi
fi

# 3. wget
echo ""
echo "[3/4] wget 確認..."
if command -v wget &>/dev/null; then
  echo "  OK: $(wget --version | head -1)"
else
  echo "  wgetをインストール中..."
  install_pkg wget
fi

# 4. Python依存パッケージ
echo ""
echo "[4/4] Python パッケージインストール..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 -m pip install -r "$SCRIPT_DIR/requirements.txt"

# ディレクトリ作成
mkdir -p "$SCRIPT_DIR/cache" "$SCRIPT_DIR/datasets"

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "起動方法:"
echo "  cd $SCRIPT_DIR"
echo "  python3 server.py"
echo ""
echo "ブラウザで http://localhost:8789 を開いてください"
echo ""
echo "--- 使い方 ---"
echo "1. Crawl タブでサイトURLを入力 → スクレイピング開始"
echo "2. 完了後、自動で .sqlite データセットが構築される"
echo "3. Datasets タブでデータセットをダウンロード"
echo "4. ホーム画面で検索"
echo ""
echo "--- オフライン共有 ---"
echo "エクスポート: Datasets → エクスポート → .tar.gz を相手に渡す"
echo "インポート: Datasets → インポート → .tar.gz を選択"

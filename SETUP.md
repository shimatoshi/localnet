# localnet 完全セットアップガイド

**localnet** はオフラインで動くローカル検索エンジン。
Webサイトを丸ごとクロールして手元に保存し、インターネットなしで全文検索・閲覧・画像検索ができる。
データセットは圧縮ファイルで人から人へ直接受け渡し可能。

---

## 目次

1. [Termux のインストール](#1-termux-のインストール)
2. [localnet のセットアップ](#2-localnet-のセット��ップ)
3. [起動と動作確��](#3-起動と動作確認)
4. [サイトのクロール](#4-サイトのクロール)
5. [データ構造](#5-データ構造)
6. [データセットの共有](#6-データセットの共���)
7. [FAQ](#7-faq)

---

## 1. Termux のインストール

**Google Play Store 版は古くて動かない。必ず F-Droid から入れること。**

1. Android のブラウザで **https://f-droid.org** を開く
2. 「Download F-Droid」→ F-Droid アプリをインストール
3. F-Droid で **Termux** を検索してインストール
4. Termux を起動
5. `termux-setup-storage` を実行してストレージ権限を付与

---

## 2. localnet のセットアップ

```bash
cp ~/storage/shared/Download/localnet.tar.gz ~
cd ~
tar xzf localnet.tar.gz
cd localnet
bash setup.sh
```

---

## 3. ��動と動作確認

```bash
cd ~/localnet
python3 server.py
```

ブラウザで **http://localhost:8789** を開く。

---

## 4. サイトのクロール

Crawl タブから URL を入力して開始。

- **深度 (Depth)**: リンクを何階層まで辿るか。0 = 無制限
- **遅延 (Delay)**: リクエスト間の秒数。1〜2秒推奨
- 広告・トラッキング系ドメインは自動除外
- 動画・GIF はスキップ（静止画はすべて取得）

---

## 5. データ構造

### 基本原則

- **1データセット = 1ドメインのクロール成果物**
- 複数サイトをまとめた「データセット」は作らない
- `cache/` ディレクトリの各サブディレクトリが1データセット

### フォルダ構成

```
cache/
  www.example.com/              ← 1データセット（= 1ドメインの全ページ）
    catalog.json                ← ページ一覧（検索用カタログ）
    images.json                 ← 画像一覧（画像検索用）
    _root/                      ← トップページ（URLパスが空のページ）
      index.html
      style_abc123.css
      logo_def456.png
    about/                      ← /about ページ
      index.html
      photo_ghi789.jpg
    blog/entry-1/               ← /blog/entry-1 ペー��
      index.html
      image1_jkl012.png
```

### ルール

- 各ページは **フォルダ単位** で保存される（page-per-folder方式）
- `index.html` + 同フォルダ内にCSS・JS・画像・フォント等のリソース
- HTMLの参照はすべて同フォルダ内の相対パス
- トップページ（URLパスなし）は `_root/` フォルダ
- `catalog.json` はカタログ生成時に自動作成され、検索に使われる
- 自作サイト（sites/）もこれと同じ構造で作成される

### 検索の仕組み

- `cache/` 内の全データセットの `catalog.json` をメモリにキャッシュ
- 検索クエリに対してタイトル・パスの部分一致で検索
- 画像検索は `images.json` を使い、alt・ファイル名・ページタイトルで検索

---

## 6. データセットの共有

### エクスポート（渡す側）

Manage タブ → サイトの「エクスポート」→ `.tar.gz` がダウンロードされる。
USB / Bluetooth / NearbyShare 等で相手に渡す。

### インポート（受け取る側）

Manage タブ → 「インポート」→ `.tar.gz` を選択。
`cache/` に展開されて即検索・閲覧可能。

### GitHub経由の共有

Datasets タブから共有データセットのダウンロードが可能。
誰かがクロールしたデータセットをアップロードしておけば、他のユーザーはDLするだけ。

---

## 7. FAQ

**Q: クロールが遅い**
→ 遅延を下げる（0.5秒未満は非推奨）。深度を制限して必要な部分だけ取る。

**Q: クロールが途中で止まった**
→ cache/ にデータは残っている。「再開 (Resume)」で続行可能。

**Q: 画像が表示されない**
→ JSで動的に読み込まれる画像は取得できない。静的なHTML内の画像は対応済み。

**Q: 検索しても結果が出ない**
→ カタログが生成されていない可能性。Manage タブで「Build」を実行。

**Q: 文字化けする**
→ サーバーがcharsetを自動検出する。検出できない場合はUTF-8として扱う。

**Q: `Address already in use` エラー**
→ `kill $(lsof -t -i :8789)` で既存プロセスを停止してから再起動。

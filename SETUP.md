# localnet 完全セットアップガイド

**localnet** はオフラインで動くローカル検索エンジン。
Webサイトを丸ごとスクレイピングして手元に保存し、インターネットなしで全文検索・閲覧できる。
データセットは圧縮ファイルで人から人へ直接受け渡し可能。

---

## 目次

1. [Termux のインストール](#1-termux-のインストール)
2. [localnet のセットアップ](#2-localnet-のセットアップ)
3. [起動と動作確認](#3-起動と動作確認)
4. [サイトのスクレイピング](#4-サイトのスクレイピング)
5. [データセットの仕組み](#5-データセットの仕組み)
6. [オフラインでデータセットを共有する](#6-オフラインでデータセットを共有する)
7. [閲覧可能なページを増やすには](#7-閲覧可能なページを増やすには)
8. [仕組みの詳細解説](#8-仕組みの詳細解説)
9. [FAQ — よくある質問とトラブルシューティング](#9-faq--よくある質問とトラブルシューティング)
10. [Linux / Windows でのセットアップ](#10-linux--windows-でのセットアップ)

---

## 1. Termux のインストール

Termux は Android 上で Linux ターミナルを動かすアプリ。
**Google Play Store 版は古くて動かない。必ず F-Droid から入れること。**

### 手順

1. Android のブラウザで **https://f-droid.org** を開く
2. 「Download F-Droid」をタップして F-Droid アプリをインストール
   - 「提供元不明のアプリ」を許可する必要がある
   - 設定 → セキュリティ → 提供元不明のアプリ → ブラウザを許可
3. F-Droid アプリを開く
4. 検索バーに **Termux** と入力
5. **Termux** (com.termux) をインストール
6. Termux を起動する

> 初回起動時に「Bootstrap packages」のダウンロードが走る。
> Wi-Fi 環境で 1〜2 分待つ。

### ストレージ権限の付与

Termux 内で以下を実行:

```bash
termux-setup-storage
```

ダイアログが出たら「許可」をタップ。
これで `~/storage/` 経由で Android の内部ストレージにアクセスできる。

---

## 2. localnet のセットアップ

### localnet.tar.gz を手に入れる

- 誰かからUSB/Bluetooth/SDカードで受け取る
- または内部ストレージにコピー済みの状態を想定

### 展開とセットアップ

```bash
# 内部ストレージからコピー（ファイルの場所は適宜変更）
cp ~/storage/shared/Download/localnet.tar.gz ~

# 展開
cd ~
tar xzf localnet.tar.gz
cd localnet

# 自動セットアップ（Python, wget, Flask を一括インストール）
bash setup.sh
```

setup.sh は以下を自動でやる:
- Python 3 がなければインストール
- pip がなければインストール
- wget がなければインストール
- Flask をインストール

全部で 2〜5 分程度。

### 手動でやる場合

```bash
pkg install python wget
pip install flask
```

---

## 3. 起動と動作確認

```bash
cd ~/localnet
python3 server.py
```

以下が表示されれば成功:

```
localnet starting on port 8789
ディレクトリ: /data/data/com.termux/files/home/localnet
```

Android のブラウザ（Chrome 等）で **http://localhost:8789** を開く。
ホーム画面が表示されたら OK。

> **起動しっぱなしにする場合:**
> Termux の通知を下にスワイプして「Acquire wakelock」をタップすると、
> バックグラウンドでも Termux が停止されなくなる。

---

## 4. サイトのスクレイピング

### 画面操作

1. 画面下の **Crawl** タブをタップ
2. **URL** に保存したいサイトのアドレスを入力
   - 例: `https://docs.python.org/ja/3/`
3. **設定を調整**（任意）:
   - **深度 (Depth)**: リンクを何階層まで辿るか。0 = 無制限
   - **遅延 (Delay)**: リクエスト間の秒数。相手サーバーに負荷をかけすぎないように 1〜2 秒推奨
   - **除外パターン**: ダウンロードしたくない URL のパターン（正規表現）
4. **開始** をタップ
5. ログがリアルタイムで表示される
6. 完了すると自動で `.sqlite` データセットが構築される

### 何が起きているか

```
[スクレイピング]
  ブラウザのフリをして (User-Agent偽装) サイトにアクセス
  → HTML, 画像, CSS を cache/{ドメイン}/ に保存
  → ページ内のリンクを辿って次のページも保存（幅優先探索）
  → 500ページごとにチェックポイント（途中経過のデータセット構築）

[データセット構築]
  cache/ のHTMLを読み取り
  → テキスト抽出、タイトル抽出
  → 画像をバイナリとしてDB内に埋め込み
  → HTML内の画像リンクをDB内部参照に書き換え
  → FTS5（全文検索インデックス）を構築
  → {ドメイン}.sqlite として保存

[検索インデックス更新]
  全データセットのテキスト部分だけを search_index.sqlite に統合
  → 検索時はこの1ファイルだけ読めば全サイト横断検索できる
```

### スクレイピングの目安時間

| サイト規模 | ページ数 | 目安時間 (遅延1秒) |
|-----------|---------|-------------------|
| 小規模サイト | 〜100 | 数分 |
| 中規模サイト | 〜1000 | 15〜30分 |
| 大規模サイト | 〜10000 | 数時間 |
| docs.python.org | 約 200 | 5分程度 |

> **途中で止めても大丈夫。**
> Crawl タブの「Sites」セクションに途中のキャッシュが残る。
> 「再開 (Resume)」ボタンで続きから取得できる。

---

## 5. データセットの仕組み

### ファイル構成

```
localnet/
├── cache/
│   └── docs.python.org/      ← 生の HTML/画像ファイル（スクレイピング結果）
│       └── docs.python.org/
│           ├── index.html
│           ├── tutorial/
│           │   ├── index.html
│           │   └── ...
│           └── _static/
│               └── py.svg
├── datasets/
│   ├── docs.python.org.sqlite ← 個別データセット（HTML+画像+FTS5）
│   └── search_index.sqlite    ← 統合検索インデックス（テキストのみ）
```

### 個別データセット ({ドメイン}.sqlite)

中身は SQLite データベース。テーブル構成:

| テーブル | 内容 |
|---------|------|
| `pages` | URL, タイトル, テキスト, gzip圧縮HTML, MIME |
| `images` | URL, バイナリデータ, MIME |
| `pages_fts` | FTS5全文検索インデックス（タイトル＋テキスト） |
| `meta` | メタ情報（ページ数, 作成日時, ソースURL） |

**ポイント:** 画像もHTMLもこの1ファイルに自己完結している。
このファイルさえあればオフラインで元サイトをほぼ再現できる。

### 統合検索インデックス (search_index.sqlite)

全データセットの **テキストだけ** を集めた軽量なDB。

| テーブル | 内容 |
|---------|------|
| `pages` | URL, ドメイン, データセット名, タイトル, テキスト |
| `pages_fts` | FTS5全文検索インデックス |

画像・HTML は含まない。検索はこの1ファイルで完結する。
サイトが 100 個あっても 1000 個あっても、検索は常に 1 回のクエリで済む。

---

## 6. オフラインでデータセットを共有する

### エクスポート（渡す側）

1. localnet を起動して **Datasets** タブを開く
2. 共有したいデータセットの **「エクスポート」** ボタンをタップ
3. `{ドメイン}.tar.gz` がダウンロードされる
4. USB / Bluetooth / SDカード / NearbyShare 等で相手に渡す

エクスポートされるのは **cache/ 内の生HTMLファイル群** を圧縮したもの。
相手側で .sqlite に変換される。

### インポート（受け取る側）

1. 受け取った `.tar.gz` を Android の内部ストレージに置く
2. localnet を起動して **Datasets** タブを開く
3. 一番下の **「インポート」** セクションで **「ファイルを選択」** をタップ
4. `.tar.gz` ファイルを選ぶ
5. 自動で展開 → `.sqlite` 構築 → 検索インデックス更新が走る
6. 完了すると検索・閲覧が可能になる

### なぜ .sqlite ではなく .tar.gz で受け渡すのか

- `.sqlite` は画像をバイナリで埋め込んでいるため圧縮効率が悪い
- `cache/` の生ファイルは HTML + 画像なので `.tar.gz` で高圧縮できる
- 受け取り側で .sqlite を構築するので、構築ロジックのバージョン違いで問題が起きない

---

## 7. 閲覧可能なページを増やすには

### 方法1: 自分でスクレイピングする

一番基本。Crawl タブから URL を入力して開始するだけ。

**ヒント:**
- 深度を制限すると特定セクションだけ取れる（例: `/tutorial/` だけ取りたいなら深度 2〜3）
- 除外パターンで不要な部分をスキップ（例: `/archive/` を除外）
- 同じサイトを再度クロールすると「再開」で差分だけ取得できる

### 方法2: 人からデータセットをもらう

tar.gz を受け取ってインポートするだけ。
スクレイピングの手間と時間が不要。

### 方法3: cache/ にファイルを直接置く

wget で手動ダウンロードしたファイルや、別ツールで保存した HTML を
`cache/{ドメイン名}/{ドメイン名}/` に配置して「Build」ボタンを押す。

```bash
# 例: wget で手動取得
cd ~/localnet
mkdir -p cache/example.com/example.com
cd cache/example.com/example.com
wget -r -l 2 -p https://example.com/
# localnet の Datasets タブ → Sites → example.com → Build
```

### 方法4: HTTrack 等の別ツールと併用

HTTrack や `curl` で取得したファイルを cache/ の正しいディレクトリ構造に配置すれば、
localnet の Build 機能でデータセット化できる。

ディレクトリ構造は `cache/{ドメイン}/{ドメイン}/` の下にサイトのパス構造をそのまま再現する。

---

## 8. 仕組みの詳細解説

### スクレイパー (crawler.py)

**2つのモードがある:**

| モード | 使用環境 | 仕組み |
|-------|---------|--------|
| wget モード | Linux / Termux | `wget --recursive` コマンドを実行。高速で堅牢 |
| Python モード | Windows | 標準ライブラリの `urllib` でBFS巡回。wget不要 |

**動作の流れ:**

1. 開始URLのHTMLを取得
2. HTML内の `<a href="...">` リンクを全部抽出
3. 同じドメイン内のリンクだけをキューに追加
4. キューから次のURLを取り出して繰り返し（幅優先探索）
5. 画像・CSS・JSも一緒にダウンロード（`--page-requisites`）
6. 広告・トラッキング系ドメインは自動除外（config.py の AD_DOMAINS リスト）
7. 500ページごとにチェックポイント（途中のデータセット構築）

**保存先:** `cache/{ドメイン}/{ドメイン}/{URLのパス}`

```
例: https://docs.python.org/3/tutorial/index.html
→   cache/docs.python.org/docs.python.org/3/tutorial/index.html
```

### 変換器 (dataset_builder.py)

cache/ の生ファイルを .sqlite に変換する。3パス構成。

**Pass 1 — HTML収集 & 画像URL抽出:**
- cache/ ディレクトリを再帰的に走査
- MIME判定でHTMLファイルだけ抽出
- 各HTML内の `<img src>`, `srcset`, `background-image: url()` を全部抽出
- ファイルパスからURLを復元

**Pass 2 — 画像をDB内に格納:**
- Pass 1 で見つけた画像URLに対応するキャッシュファイルを探す
- バイナリを読み込んで images テーブルに INSERT
- URL → DB内ID のマッピングを構築

**Pass 3 — HTML書き換え & ページ格納:**
- 各HTMLの画像リンクを `localnet://img/{id}` 形式に書き換え
  - 例: `<img src="https://example.com/logo.png">` → `<img src="localnet://img/42">`
- HTMLを gzip 圧縮して pages テーブルに格納
- テキスト本文とタイトルも抽出して格納
- FTS5 トリガーにより、INSERT と同時に全文検索インデックスが自動構築される

**最後:** VACUUM でDBを最適化して完成。

### 検索の流れ

```
ユーザーが検索バーに入力
  ↓
search_index.sqlite に対して FTS5 MATCH クエリ（1回）
  ↓
結果リスト表示（URL, タイトル, スニペット, データセット名）
  ↓
ユーザーが結果をタップ
  ↓
{データセット名}.sqlite を開いてページのHTMLを取得
  ↓
gzip解凍 → 画像参照を解決 → iframe内に表示
```

---

## 9. FAQ — よくある質問とトラブルシューティング

### セットアップ編

**Q: `bash setup.sh` で「permission denied」が出る**

```bash
chmod +x setup.sh
bash setup.sh
```

**Q: `pkg install` が「Unable to locate package」で失敗する**

Termux のパッケージリストが古い。更新してからリトライ:

```bash
pkg update
pkg upgrade
bash setup.sh
```

**Q: `pip install flask` で「externally-managed-environment」エラーが出る**

新しい Python で出るエラー。以下で解決:

```bash
pip install flask --break-system-packages
```

または setup.sh が自動で対処する。

**Q: F-Droid からTermux がインストールできない**

「提供元不明のアプリ」が許可されているか確認。
設定 → アプリ → 特別なアクセス → 不明なアプリのインストール → F-Droid → 許可

### 起動編

**Q: `python3 server.py` で「Address already in use」エラー**

別のプロセスがポート 8789 を使っている。

```bash
# 使っているプロセスを確認
lsof -i :8789

# 強制終了
kill $(lsof -t -i :8789)

# 再起動
python3 server.py
```

または `config.py` の PORT を別の番号（例: 8790）に変更。

**Q: ブラウザで `localhost:8789` を開いても繋がらない**

- Termux で `python3 server.py` が実行中か確認
- `http://127.0.0.1:8789` も試す
- 別のアプリ（VPN等）がローカル通信を遮断していないか確認

**Q: バックグラウンドで動かし続けたい**

Termux の通知バーから「Acquire wakelock」をタップ。
さらに確実にするには:

```bash
# Termux:Boot をF-Droidからインストールした上で
mkdir -p ~/.termux/boot
echo '#!/data/data/com.termux/files/usr/bin/bash
cd ~/localnet && python3 server.py &' > ~/.termux/boot/start-localnet.sh
chmod +x ~/.termux/boot/start-localnet.sh
```

### スクレイピング編

**Q: スクレイピングが遅い**

- 遅延 (Delay) を下げる（ただし 0.5 秒未満はサーバーに負荷がかかるため非推奨）
- 深度を制限して必要な部分だけ取る
- 除外パターンで不要なセクションをスキップ

**Q: スクレイピングが途中で止まった / エラーになった**

データは cache/ に残っている。Crawl タブの Sites セクションから「再開 (Resume)」で続行可能。
完全にやり直したい場合は「Build」で cache/ から .sqlite を再構築できる。

**Q: 「exit=6: 認証が必要」と表示される**

ログインが必要なサイト。localnet では対応していない。
公開ページのみスクレイピング可能。

**Q: 画像が取れていない / データセットに画像がない**

- `--page-requisites` (wget) により画像もダウンロードされるが、
  JavaScriptで動的に読み込まれる画像は取得できない
- amp-img タグの画像は対応済み
- CSS background-image も対応済み
- srcset（レスポンシブ画像）も対応済み

**Q: 特定のページだけ保存したい**

深度を 0 にすると開始URLのみ取得。
または手動で cache/ にファイルを置いて Build する方法を推奨。

### データセット編

**Q: データセットの構築が失敗する**

cache/ 内のファイルが壊れている可能性がある。

```bash
# cache内のファイル数を確認
find cache/ドメイン名 -type f | wc -l

# HTMLファイルがあるか確認
find cache/ドメイン名 -name "*.html" | head -5
```

HTMLファイルが0個なら、スクレイピングが正常に行われていない。

**Q: データセットが大きすぎる**

画像がDBに埋め込まれるため大きくなる。
画像の少ないテキスト中心のサイト（ドキュメント系）なら小さく済む。

**Q: 検索しても結果が出ない**

- 検索インデックスが古い可能性がある。Datasets タブでデータセットを再ダウンロードすると検索インデックスも更新される
- 日本語の検索は単語単位で入力するとヒットしやすい
  - 例: 「機械学習の基礎」より「機械学習」のほうがヒットする

**Q: インポートしたのに検索結果に出てこない**

インポート完了後、検索インデックスが自動更新される。
「構築中」の表示が消えるまで待つ。

### 共有編

**Q: エクスポートボタンがない**

サーバーが起動していてオンライン状態であることを確認。
エクスポートはサーバー側の cache/ から tar.gz を生成するため、サーバーとの通信が必要。

**Q: .tar.gz が壊れているとインポートで言われる**

ファイルの転送中に破損した可能性がある。再度受け取りを試す。
zip 形式は非対応。必ず .tar.gz / .tgz を使う。

---

## 10. Linux / Windows でのセットアップ

### Linux (Ubuntu / Debian)

```bash
tar xzf localnet.tar.gz
cd localnet
bash setup.sh
python3 server.py
```

### Linux (他のディストリビューション)

```bash
# 手動で依存をインストール
# Fedora: sudo dnf install python3 python3-pip wget
# Arch:   sudo pacman -S python python-pip wget

tar xzf localnet.tar.gz
cd localnet
pip install flask
python3 server.py
```

### Windows

wget は不要。Python 内蔵のクローラーが自動で使われる。

```
1. https://www.python.org/ から Python 3 をインストール
   - インストール時に「Add Python to PATH」にチェックを入れる
2. コマンドプロンプトを開く
3. localnet.tar.gz を展開（7-Zip 等を使用）
4. cd localnet
5. pip install flask
6. python server.py
```

ブラウザで `http://localhost:8789` を開く。

# Service Worker — オフライン配信の仕組み

## SWとは何か

ブラウザとサーバーの間に立つ**門番**。ブラウザの全てのfetchリクエストを横取りできる。

```
通常時:
  ブラウザ ──fetch──> SW(門番) ──> サーバー
                       ↓
                  通過するレスポンスのコピーをCache APIに保存

オフライン時:
  ブラウザ ──fetch──> SW(門番) ──✕ サーバー到達不可
                       ↓
                  キャッシュにコピーがあれば代わりに返す
```

## このアプリでの役割

localnetはサーバー(Flask)でサイトをクロールし、PWAで持ち出してオフライン閲覧するアプリ。
SWは「持ち出し」を成立させる必須機能。

### オフライン閲覧が成立する流れ

```
1. 自宅(オンライン): 「データセットDL」ボタンを押す
   ├─ カタログJSON → IndexedDB に保存（オフライン検索用）
   └─ 全HTMLページを1個ずつ fetch() する
        ↓
       SWがfetchを横取り → Cache APIに自動保存
       （全ページを「門の前を通過」させてコピーを取らせる）

2. 外出先(オフライン): PWAを開く
   ├─ UI (JS/CSS/HTML) → SWキャッシュから配信
   ├─ 検索 → IndexedDBのカタログをフロントのJSが検索
   └─ ページ閲覧 → SWキャッシュからHTMLを返す
```

## キャッシュ戦略

SWのfetchハンドラには複数の戦略がある。

### Network-First（このアプリのデフォルト）
```
リクエスト → ネットワーク試す
  ├─ 成功 → レスポンス返す + キャッシュに保存
  └─ 失敗 → キャッシュから返す（なければエラー）
```
- オンライン時は常に最新データ
- オフライン時はキャッシュで動く
- 静的ファイル(JS/CSS)やHTMLページに使用

### Cache-First（画像向け、dmonline2で使用）
```
リクエスト → キャッシュにある？
  ├─ ある → キャッシュから返す（ネットワーク不要）
  └─ ない → ネットワークから取得 + キャッシュに保存
```
- 変更されないリソース（画像など）に最適
- ネットワーク通信を減らせる

### このアプリ（sw.js）の実装
```
/api/* → Network-First（APIはキャッシュしない。失敗時は503エラー）
その他  → Network-First + キャッシュフォールバック
```

## オフラインで動く機能の対応表

| 機能 | オンライン時 | オフライン時 | データの在処 |
|------|-------------|-------------|-------------|
| UI表示 | サーバーからJS/CSS | SWキャッシュ | Cache API |
| ページ閲覧 | Flask `/api/cache/` | SWキャッシュ | Cache API |
| 検索 | Flask `/api/search` | フロントJS実行 | IndexedDB (カタログ) |
| 履歴 | IndexedDB | IndexedDB | IndexedDB |
| ブックマーク | IndexedDB | IndexedDB | IndexedDB |
| クロール | Flask + wget | **使用不可** | — |
| エクスポート | Flask | **使用不可** | — |

## SWのライフサイクル

```
1. install  — 初回登録時。skipWaiting()で即座にアクティブ化
2. activate — 古いキャッシュバージョンを削除。clients.claim()で即座に制御開始
3. fetch    — 全リクエストを横取り。戦略に従って処理
```

バージョン管理: `CACHE_NAME = 'localnet-v10'` を更新すると、
activateイベントで古いバージョンのキャッシュが自動削除される。

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `frontend/public/sw.js` | Service Worker本体 |
| `frontend/src/main.tsx` | SW登録 (`navigator.serviceWorker.register`) |
| `frontend/src/screens/DatasetsScreen.tsx` | DLボタン（SWにコピーを取らせるfetch） |
| `frontend/src/stores/db.ts` | IndexedDB（カタログ・履歴・ブックマーク） |
| `frontend/src/hooks/useOnline.ts` | オンライン/オフライン検知 |
| `frontend/src/screens/SearchScreen.tsx` | 検索のオン/オフライン分岐 |

## ストレージの構造

ブラウザはオリジン（プロトコル+ドメイン+ポート）ごとに隔離されたサンドボックスを持つ。

```
http://localhost:8789 のサンドボックス
├─ IndexedDB "localnet"
│   ├─ catalogs   ← 目次（検索用）
│   ├─ history    ← 閲覧履歴
│   └─ bookmarks  ← ブックマーク
│
└─ Cache API "localnet-v10"
    ├─ /api/cache/tansuigyo.net/index.html → レスポンス丸ごと
    ├─ /assets/index-xxxxx.js              → レスポンス丸ごと
    └─ ...（DL時にfetchした全URL分）
```

IndexedDBは**目次**、Cache APIは**本の中身**。
検索は目次を引き、閲覧は本棚から実物を出す。

DevToolsで確認: `F12` → `Application` → `IndexedDB` / `Cache Storage`

## プラットフォーム別のストレージ挙動

### Android

PWAとChromeは**同じストレージ領域を共有**する。

```
Chrome で開く  → IndexedDB: http_localhost_8789/
PWA で開く     → IndexedDB: http_localhost_8789/  ← 同じもの
```

- Chromeで落としたデータセットはPWAからも見える（逆も同様）
- **ストレージ上限: デバイス空き容量の最大80%**（64GBスマホで空き30GB → 約24GB）
- サイト丸ごとオフラインで持ち歩く用途に十分な容量

**注意**:
- Chromeの「サイトデータ削除」→ PWAのデータも巻き添えで消える
- Chromeをアンインストール → PWAのデータも消える
- `navigator.storage.persist()` が通っていればOS側の自動削除は防げる

### iOS

PWAとSafariで**ストレージが完全に分離**される。

```
Safari で開く  → IndexedDB: http_localhost_8789/
PWA で開く     → IndexedDB: http_localhost_8789/  ← 別物
```

- SafariでDLしたデータセットはPWAからは見えない
- **PWA側で改めてデータセットDLが必要**
- PWAを削除するとそのストレージも消える
- Safariでログインしてても、PWAでは未ログイン状態

**致命的な制限**:
- **PWAのストレージ上限: 約50MB**（Safari本体は約1GB）
- サイト丸ごとクロールしたデータには小さすぎる可能性が高い
- HTMLページ数百枚で埋まるレベル

### まとめ

| | Android | iOS |
|---|---|---|
| PWAとブラウザのストレージ | **共有** | **分離** |
| ストレージ上限 | 空き容量の80% | 約50MB (PWA) |
| ブラウザでDL → PWAで使える？ | はい | いいえ |
| PWA削除でデータ消える？ | いいえ（Chrome側に残る） | はい |
| このアプリの実用性 | **◎** | **△（容量不足の可能性）** |

## 注意点

- SWは**HTTPS**か**localhost**でしか動かない
- SWの更新はブラウザの再起動やハードリロードが必要な場合がある
- IndexedDBの永続化には `navigator.storage.persist()` が必要（main.tsxで実行済み）

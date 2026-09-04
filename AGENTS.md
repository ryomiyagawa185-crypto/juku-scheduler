# juku-scheduler — エージェント向けプロジェクト指示

このファイルは Grok CLI（`@xai-official/grok`）が **Project Instructions** として自動で読み込む。
Claude Code は `CLAUDE.md` を読むため、両者に同じ規約を効かせたい場合は本ファイルを正本とし、
`CLAUDE.md` からは本ファイルを参照させること。

## 1. このリポジトリは何か

武蔵野個別指導塾の **授業スケジューラ（PWA）**。ビルド工程は無い。HTML を直接配信するだけの静的サイト。

| パス | 役割 |
|---|---|
| `index.html` | 本体。単一ファイル完結（約 5,900 行 / 約 380KB）。CSS・JS はすべてインライン |
| `サーバー版アプリ.html` | 同期版（Google Apps Script 連携前提）。約 2,600 行 |
| `juku-github更新/sync-app.html` | 同期版の別系統。約 2,200 行 |
| `sw.js` | Service Worker。cache-first + stale-while-revalidate |
| `manifest.webmanifest` | PWA マニフェスト |
| `icon-192.png` / `icon-512.png` / `apple-touch-icon.png` | アイコン |

## 2. 触る前に必ず守ること

### 2-1. `sw.js` のキャッシュ版数を上げる

`index.html`・`manifest.webmanifest`・アイコンのいずれかを変更したら、
`sw.js` 冒頭の定数を **必ず** インクリメントする。

```js
const CACHE = 'juku-scheduler-v2.44.0';   // ← 変更のたびに上げる
```

`activate` で旧 `CACHE` キーを削除する実装のため、ここを上げないと
インストール済み端末が古い `index.html` を掴んだまま更新されない。
実運用中の塾スタッフ端末に直撃するので、これは任意ではなく必須。

### 2-2. 巨大 HTML を全文書き換えしない

`index.html` は 380KB の単一ファイル。全文再生成は絶対に行わず、
対象箇所だけを検索して差分編集する（`Edit` / `sed` 相当のピンポイント置換）。
全文を出力させると破損・欠落のリスクが高く、トークンも浪費する。

### 2-3. 外部依存を持ち込まない

現状 `index.html` の外部 URL 参照は **0 件**（CDN・外部フォント・外部スクリプトなし）。
完全自己完結でオフライン動作することが PWA としての前提なので、
CDN からの `<script src>` / `<link href>` 追加は行わない。必要ならインライン化する。

### 2-4. ファイル名の Unicode 正規化に注意

`サーバー版アプリ.html` は **NFD 正規化**（macOS 由来）で格納されている。
Linux のシェルから NFC のリテラルで `grep`/`cat` を叩くと
`No such file or directory` になる。以下で回避すること。

```bash
# NG: シェルに直接日本語リテラルを書く
grep foo サーバー版アプリ.html

# OK: グロブで拾う
grep foo *アプリ.html
# OK: Python など正規化に依存しない手段で開く
python3 -c "import glob;print(glob.glob('*.html'))"
```

## 3. コーディング規約

- UI 文言・コメントはすべて **日本語**。`<html lang="ja">` を維持する
- インライン CSS はファイル冒頭の `:root` カスタムプロパティ（`--accent`, `--danger` 等）を使い、
  色をハードコードしない
- 既存のコードスタイル（インデント・命名・コメント密度）に合わせる。整形し直さない
- 依存追加・フレームワーク導入・ビルド工程の新設は、明示的に依頼された場合のみ

## 4. 検証

ビルドもテストも無いため、変更後は最低限これを行う。

```bash
npx --yes http-server . -p 8080 -c-1
# → http://localhost:8080 を開き、ブラウザのコンソールにエラーが出ていないことを確認
```

Service Worker の挙動を確認する場合は、DevTools の Application → Service Workers で
「Update on reload」を有効にするか、一度 Unregister してから再読み込みする。

## 5. 禁止事項

- API キー・トークン・スプレッドシート ID・個人情報（生徒名・保護者連絡先）を
  HTML やコミットに直接書き込まない
- `main` への直接 push を行わない。作業ブランチで PR を出す
- 生徒データを含む実データファイルをコミットしない

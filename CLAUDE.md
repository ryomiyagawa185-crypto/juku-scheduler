# CLAUDE.md

このリポジトリの作業規約は **[`AGENTS.md`](./AGENTS.md)** を正本とする。
編集前に必ず読むこと。

特に次の 4 点は事故に直結する。

1. `index.html` / `manifest.webmanifest` / アイコンを変更したら、`sw.js` の
   `CACHE = 'juku-scheduler-vX.Y.Z'` を **必ず** インクリメントする
2. `index.html`（約 380KB の単一ファイル）は全文書き換えせず、差分編集する
3. 外部 URL 参照（CDN 等）を追加しない。現状 0 件のオフライン完結構成を維持する
4. `サーバー版アプリ.html` はファイル名が NFD 正規化されている。シェルから
   日本語リテラルで指定すると `No such file or directory` になるため、
   グロブ（`*アプリ.html`）で拾う

Grok CLI も本ファイルと `AGENTS.md` の両方を Project Instructions として読み込む。
セットアップと使い方は [`docs/grok-cli.md`](./docs/grok-cli.md) を参照。

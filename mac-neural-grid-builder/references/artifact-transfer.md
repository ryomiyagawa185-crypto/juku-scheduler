# artifact-transfer — 成果物転送

## 手順（§20・`artifact_store.transfer`）

```
一時名で転送 → checksum 確認 → 原子的に正式名へ改名（os.replace）
```

確認項目: ファイルサイズ・空き容量・checksum・一時ファイル・転送途中の中断・同名ファイル・
上書き・機密性・転送元と転送先。checksum 不一致は破損/改竄として拒否。

## 検証（§29）

ノードからの成果物も未信頼として扱う。`artifact_store.collect` は `manifest.json` の checksum と
実ファイルの checksum を突き合わせ、不一致なら例外。symlink 書込を拒否し、作業ディレクトリ外を参照しない。

## 中央集約

タスク output/ の成果物を検証後、`artifacts/JOB/` へ `task_id__name` で集約し、DB に
`artifact_id/checksum/size` を登録する。集約タスク（merge-summaries 等）は control ノードで実行。

## 転送方式

- MVP（localhost）: `LocalTransport.put_file`（copy2 + checksum）。
- リモート: rsync over SSH / SFTP を Phase 2 で（`allow_remote` 承認後）。stdin/stdout JSON プロトコルも
  候補。初期版は不要な常駐サーバーを増やさない（§9）。

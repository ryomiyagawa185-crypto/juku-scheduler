"""データ分類に基づく出力先の強制。

扱うのが訴訟記録（privileged）と未成年の生徒データ（pii）である以上、
「どこに書いてよいか」はスキルの自由にしてはいけない。
artifacts/open/ だけが外部同期の対象で、pii と privileged は同期しない。
"""

from __future__ import annotations

import posixpath

DATA_CLASSES = ("public", "internal", "pii", "privileged")

ROOTS = {
    "public": "artifacts/open",
    "internal": "artifacts/open",
    "pii": "artifacts/pii",
    "privileged": "artifacts/privileged",
}

# 保持期間（日）。None は自動削除しない
RETENTION_DAYS = {
    "public": 30,
    "internal": 30,
    "pii": 90,
    "privileged": None,
}

SYNCED_ROOTS = ("artifacts/open",)


class ClassificationError(ValueError):
    pass


def root_for(data_class: str) -> str:
    if data_class not in ROOTS:
        raise ClassificationError(f"未知の data_class: {data_class}")
    return ROOTS[data_class]


def is_synced(path: str) -> bool:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    return any(normalized.startswith(root + "/") or normalized == root for root in SYNCED_ROOTS)


def output_path_allowed(data_class: str, path: str) -> bool:
    """1本のパスが data_class に許された領域に収まっているか。"""
    root = root_for(data_class)
    raw = path.replace("\\", "/")
    if raw.startswith("/") or ".." in raw.split("/"):
        return False  # 絶対パスと親参照は許さない
    normalized = posixpath.normpath(raw)
    return normalized == root or normalized.startswith(root + "/")


def check_outputs(data_class: str, paths) -> list[str]:
    """許されないパスの一覧を返す。空リストなら適合。"""
    return [p for p in paths if not output_path_allowed(data_class, p)]

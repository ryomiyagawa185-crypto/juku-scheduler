"""正規化ハッシュ。承認の内容束縛（TOCTOU 対策）の基礎になる。

同じ意味の入力が同じハッシュになる必要がある。キー順・空白・
Unicode 正規化のゆらぎでハッシュが変わると、承認が意味なく失効する。
逆に緩すぎると、内容が変わったのに承認が生き残る。
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

PREFIX = "sha256:"


def canonical(value: Any) -> str:
    """JSON を正規化して文字列にする（キー順固定・NFC 正規化・空白なし）。"""
    normalized = _normalize(value)
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_normalize(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def hash_value(value: Any) -> str:
    """任意の JSON 化可能な値のハッシュ。"""
    digest = hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    return PREFIX + digest


def hash_text(text: str) -> str:
    digest = hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()
    return PREFIX + digest


def hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return PREFIX + h.hexdigest()


def target_hash(inputs: Any, body: str | None = None) -> str:
    """承認対象のハッシュ。

    外部送信ゲートでは本文まで含める。inputs だけを見ていると
    「同じ宛先・同じ件名で本文だけ差し替わった」を検出できない。
    """
    return hash_value({"inputs": inputs, "body": body})

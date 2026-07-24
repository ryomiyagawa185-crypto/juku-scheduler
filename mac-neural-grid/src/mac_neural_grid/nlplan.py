# -*- coding: utf-8 -*-
"""nlplan — 自然言語指示 → 構造化ジョブ計画（仕様 §14/§26）。

決定的なヒューリスティックで intent と制約を抽出し、**直接シェルへ変換せず** 構造化計画を返す。
危険・曖昧・外部送信・削除・上書きを含む場合は requires_approval を立てる。解析に失敗したら
勝手に推測して実行せず、計画（と needs_clarification）を提示する。

注: 本モジュールは LLM を呼ばない決定的パーサ。より高度な意図解釈は上流の認知スキル
（brain-cognitive-architecture-jp）や Claude Code 本体に委ね、ここは安全な下限を担保する。
"""

import re

_INTENTS = [
    ("transcribe-video", ("文字起こし", "書き起こし", "transcribe", "字幕"),
     {"executor": "shell", "capabilities": ["ffmpeg"]}),
    ("summarize-documents", ("要約", "まとめて", "summary", "summarize"),
     {"executor": "document-summary", "capabilities": []}),
    ("ocr-documents", ("ocr", "文字認識", "スキャン", "読み取り"),
     {"executor": "ocr", "capabilities": ["pdftotext"]}),
    ("checksum", ("チェックサム", "ハッシュ", "checksum", "hash", "整合性"),
     {"executor": "checksum", "capabilities": []}),
    ("convert-media", ("変換", "convert", "エンコード"),
     {"executor": "ffmpeg", "capabilities": ["ffmpeg"]}),
]
_DANGER = ("削除", "消して", "delete", "rm ", "上書き", "overwrite", "移動", "mv ",
           "sudo", "権限", "chmod", "外部", "送信", "アップロード", "api", "全台", "all nodes")
_CONFIDENTIAL = ("機密", "秘密", "confidential", "外部ai", "外部api", "ローカルのみ",
                 "ローカルだけ", "local only", "外部に出さ")


def _num(text, default=None):
    m = re.search(r"(\d+)\s*台", text)
    return int(m.group(1)) if m else default


def plan(prompt, inputs=None):
    """自然言語からジョブ計画（構造化）を作る。実行はしない。"""
    text = str(prompt or "").lower()
    intent, exec_hint = "generic", {"executor": "document-summary", "capabilities": []}
    for name, keys, hint in _INTENTS:
        if any(k.lower() in text for k in keys):
            intent, exec_hint = name, hint
            break
    apple_only = ("apple silicon" in text or "m1" in text or "m2" in text
                  or "m3" in text or "arm" in text)
    confidential = any(k in text for k in _CONFIDENTIAL)
    dangerous = any(k in text for k in _DANGER)
    max_nodes = _num(text, None)

    requirements = {"capabilities": exec_hint["capabilities"]}
    if apple_only:
        requirements["architecture"] = "arm64"

    job = {
        "name": intent,
        "policy": "confidential-local-only" if confidential else None,
        "tasks": [{
            "type": intent, "executor": exec_hint["executor"],
            "input_glob": (inputs or "./*"),
            "split": "per-file",
            "requirements": requirements,
        }],
        "aggregation": {"type": "merge-summaries", "node": "control"},
    }
    return {
        "intent": intent,
        "job": job,
        "constraints": {"max_nodes": max_nodes, "external_api": not confidential,
                        "apple_silicon_only": apple_only, "confidential": confidential},
        "requires_approval": dangerous,
        "needs_clarification": intent == "generic",
        "note": ("危険/外部送信/削除/上書きの可能性 → 実行前に承認が必要（§14/§15）"
                 if dangerous else
                 "意図が曖昧 → 実行せず計画を提示。明確化を求める（§26）"
                 if intent == "generic" else
                 "計画を確認のうえ job run で実行してください。"),
    }

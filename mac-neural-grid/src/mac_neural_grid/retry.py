# -*- coding: utf-8 -*-
"""retry — 失敗分類と再試行判定（仕様 §21）。同じ失敗を無限に繰り返さない。

再試行可能な失敗（transient/resource_exhaustion/node_offline）のみ、別ノードで再実行する。
"""

RETRYABLE = {"transient", "resource_exhaustion", "node_offline", "lost"}
NON_RETRYABLE = {"invalid_input", "permission_denied", "dependency_missing",
                 "policy_denied", "deterministic_failure"}


def classify(result):
    """executor/worker 結果から失敗クラスを確定する。"""
    fc = result.get("failure_class")
    if fc:
        return fc
    status = result.get("status")
    if status == "timed_out":
        return "transient"
    if status == "succeeded":
        return None
    return "unknown"


def is_retryable(failure_class):
    return failure_class in RETRYABLE


def should_retry(failure_class, attempt_no, max_retries):
    return is_retryable(failure_class) and attempt_no < max_retries


def backoff_seconds(attempt_no, base=2.0, cap=60.0):
    """指数バックオフ（決定的・上限あり）。"""
    return min(cap, base ** attempt_no)

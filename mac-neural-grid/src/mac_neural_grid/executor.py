# -*- coding: utf-8 -*-
"""executor — 実行方法の抽象化（仕様 §6/§12/§17）。

executor allowlist で実行体を限定し、argv 配列・作業ディレクトリ制限・timeout・出力上限を課す。
決定的タスク（checksum・document-summary の抽出要約）は AI に任せず決定的に処理する（§12）。
capability/policy でゲートされた executor（ffmpeg/ocr/local-llm/external-api/claude-code）は、
条件を満たさなければ dependency_missing / policy_denied で*クリーンに失敗*し、外部送信はしない。
"""

import os
import re

from . import security
from .transport import LocalTransport


class ExecContext(object):
    def __init__(self, dirs, node, limits, capabilities, policy):
        self.dirs = dirs                      # {input, work, output, logs}
        self.node = node
        self.limits = limits or {}
        self.capabilities = capabilities or {}
        self.policy = policy or {}
        self.transport = LocalTransport(node)


def _artifact(ctx, name, data_bytes):
    path = security.safe_join(ctx.dirs["output"], name)
    security.atomic_write_bytes(path, data_bytes)
    return {"name": name, "path": path, "checksum": security.sha256_file(path),
            "size_bytes": len(data_bytes)}


def _ok(artifacts=None, stdout="", stderr="", duration=0.0, exit_code=0):
    return {"status": "succeeded", "exit_code": exit_code,
            "failure_class": None, "artifacts": artifacts or [],
            "stdout_excerpt": stdout[:2000], "stderr_excerpt": stderr[:2000],
            "duration_s": duration}


def _fail(failure_class, stderr="", exit_code=1, duration=0.0):
    return {"status": "failed", "exit_code": exit_code, "failure_class": failure_class,
            "artifacts": [], "stdout_excerpt": "", "stderr_excerpt": stderr[:2000],
            "duration_s": duration}


def _inputs(spec):
    inp = spec.get("input")
    if inp is None:
        return []
    return inp if isinstance(inp, list) else [inp]


# ---------- 決定的 executor（オフラインで完全動作）----------

_SENT_SPLIT = re.compile(r"(?<=[。．.!?！？])\s*")


def exec_document_summary(ctx, spec):
    """決定的な抽出要約（AI 非使用）。各入力テキストの冒頭文＋統計を出力（§12）。

    機密ジョブでも外部送信ゼロ。将来 policy が許し local-llm がある場合のみ AI 経由に切替える設計。
    """
    arts, start = [], _clock()
    n_sent = int((spec.get("params") or {}).get("sentences", 3))
    for src in _inputs(spec):
        real = security.assert_within(ctx.dirs["input"], src) if os.path.isabs(src) \
            else security.safe_join(ctx.dirs["input"], src)
        if not os.path.exists(real):
            return _fail("invalid_input", "入力が見つからない: %s" % src)
        text = open(real, encoding="utf-8", errors="replace").read()
        sents = [s for s in _SENT_SPLIT.split(text) if s.strip()]
        words = len(text.split())
        lines = text.count("\n") + 1
        summary = "# 要約: %s\n\n" % os.path.basename(real)
        summary += "".join("- %s\n" % s.strip() for s in sents[:n_sent])
        summary += "\n---\n統計: %d 文字 / 約 %d 語 / %d 行 / %d 文（抽出型・決定的・AI非使用）\n" % (
            len(text), words, lines, len(sents))
        arts.append(_artifact(ctx, os.path.basename(real) + ".summary.md",
                              summary.encode("utf-8")))
    return _ok(arts, stdout="summarized %d file(s)" % len(arts), duration=_since(start))


def exec_checksum(ctx, spec):
    arts, start = [], _clock()
    lines = []
    for src in _inputs(spec):
        real = security.safe_join(ctx.dirs["input"], src) if not os.path.isabs(src) \
            else security.assert_within(ctx.dirs["input"], src)
        if not os.path.exists(real):
            return _fail("invalid_input", "入力が見つからない: %s" % src)
        lines.append("%s  %s" % (security.sha256_file(real), os.path.basename(real)))
    arts.append(_artifact(ctx, "checksums.txt", ("\n".join(lines) + "\n").encode("utf-8")))
    return _ok(arts, stdout="checksummed %d file(s)" % len(_inputs(spec)),
               duration=_since(start))


def exec_shell(ctx, spec):
    argv = spec.get("argv") or (spec.get("params") or {}).get("argv")
    if not argv:
        return _fail("invalid_input", "shell executor には argv が必要")
    start = _clock()
    try:
        r = ctx.transport.run(argv, cwd=ctx.dirs["work"],
                              timeout=ctx.limits.get("timeout_s", 600),
                              max_output_bytes=ctx.limits.get("max_output_bytes", 1 << 20))
    except security.SecurityError as exc:
        return _fail("permission_denied", str(exc))
    if r.get("spawn_error"):
        return _fail("dependency_missing", r["stderr"], exit_code=127)
    arts = []
    if r["stdout"]:
        arts.append(_artifact(ctx, "stdout.txt", r["stdout"].encode("utf-8")))
    if r["timed_out"]:
        return {"status": "timed_out", "exit_code": 124, "failure_class": "transient",
                "artifacts": arts, "stdout_excerpt": r["stdout"][:2000],
                "stderr_excerpt": r["stderr"][:2000], "duration_s": r["duration_s"]}
    if r["exit_code"] != 0:
        return {"status": "failed", "exit_code": r["exit_code"],
                "failure_class": "deterministic_failure", "artifacts": arts,
                "stdout_excerpt": r["stdout"][:2000], "stderr_excerpt": r["stderr"][:2000],
                "duration_s": r["duration_s"]}
    return _ok(arts, r["stdout"], r["stderr"], r["duration_s"])


def exec_python(ctx, spec):
    params = spec.get("params") or {}
    code = params.get("code")
    if code is None:
        return _fail("invalid_input", "python executor には params.code が必要")
    return exec_shell(ctx, {"argv": ["python3", "-c", code]})


# ---------- capability / policy でゲートされた executor（クリーンに失敗）----------

def _require_tool(ctx, tool):
    return bool((ctx.capabilities.get("tools") or {}).get(tool))


def exec_ffmpeg(ctx, spec):
    if not _require_tool(ctx, "ffmpeg"):
        return _fail("dependency_missing", "ffmpeg 未導入のノード")
    argv = ["ffmpeg"] + list((spec.get("params") or {}).get("args", []))
    return exec_shell(ctx, {"argv": argv})


def exec_ocr(ctx, spec):
    tool = "pdftotext" if _require_tool(ctx, "pdftotext") else (
        "tesseract" if _require_tool(ctx, "tesseract") else None)
    if not tool:
        return _fail("dependency_missing", "OCR ツール（pdftotext/tesseract）未導入")
    return _fail("dependency_missing",
                 "OCR executor は Phase 2（ツールは検出済み: %s）" % tool)


def exec_local_llm(ctx, spec):
    if not _require_tool(ctx, "ollama"):
        return _fail("dependency_missing", "ローカル推論環境（ollama 等）未導入")
    # 実運用は ollama へ argv 実行。外部送信は一切しない。MVP は未実行の設計スタブ。
    return _fail("dependency_missing", "local-llm executor は Phase 2（ollama 検出済み）")


def exec_external_api(ctx, spec):
    # policy が明示的に許可しない限り外部 AI API を使わない（§12/§30）。
    if not ctx.policy.get("external_ai_api"):
        return _fail("policy_denied",
                     "外部 AI API はポリシーで禁止（confidential/既定）。ローカル/決定的処理へ")
    return _fail("policy_denied",
                 "external-api executor は明示承認＋Phase 2 実装が必要（本 MVP は送信しない）")


def exec_claude_code(ctx, spec):
    if not (ctx.capabilities.get("tools") or {}).get("claude_code"):
        return _fail("dependency_missing", "Claude Code CLI 未導入のノード")
    return _fail("dependency_missing", "claude-code executor は Phase 2")


def exec_custom_script(ctx, spec):
    argv = spec.get("argv")
    if not argv:
        return _fail("invalid_input", "custom-script には argv が必要")
    return exec_shell(ctx, {"argv": argv})


REGISTRY = {
    "document-summary": exec_document_summary,
    "checksum": exec_checksum,
    "shell": exec_shell,
    "python": exec_python,
    "ffmpeg": exec_ffmpeg,
    "ocr": exec_ocr,
    "local-llm": exec_local_llm,
    "external-api": exec_external_api,
    "claude-code": exec_claude_code,
    "custom-script": exec_custom_script,
}


def run_executor(name, ctx, spec):
    fn = REGISTRY.get(name)
    if fn is None:
        return _fail("invalid_input", "未知の executor: %s" % name)
    try:
        return fn(ctx, spec)
    except security.SecurityError as exc:
        return _fail("permission_denied", str(exc))
    except Exception as exc:  # noqa: BLE001 — executor 境界で失敗を分類して返す
        return _fail("unknown", "%s: %s" % (type(exc).__name__, exc))


def _clock():
    import time
    return time.monotonic()


def _since(start):
    import time
    return round(time.monotonic() - start, 3)

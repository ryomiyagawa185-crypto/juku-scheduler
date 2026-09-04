# -*- coding: utf-8 -*-
"""synapse_bridge — 関係学習・可塑性・忘却を担う既存スキル skill-synapse-jp の再利用。

本アーキテクチャは「関係グラフ（共起・NPMI・位相・Hebbian/STDP・恒常性・剪定）」を
一から作り直さず、既存の skill-synapse-jp を一モジュールとして委譲する（生成プロンプト
末尾の設計方針）。本ブリッジは:
  - 疎結合: synapse が無くても本体は自己完結して動く（安全critical な抑制性エッジは
    本体 inhibition.py が独立に保持する）。
  - 読取優先: connectome.json は派生物として読み取り、方策選択の弱い証拠に使える。
  - 記録は best-effort: 共起の記録は synapse の CLI/モジュールへ委譲する（失敗しても
    本体の処理は止めない）。

これは統合の“継ぎ目”であり、synapse を必須依存にはしない。
"""

import os
import subprocess
import sys

from . import secure_io


def synapse_skill_dir():
    return os.environ.get("BRAIN_SYNAPSE_DIR") or os.path.expanduser(
        "~/.claude/skills/skill-synapse-jp")


def available():
    d = synapse_skill_dir()
    return os.path.isdir(os.path.join(d, "scripts", "synapse"))


def _synapse_memory_dir():
    # synapse 側の可変記憶ルート（既定は synapse スキルの規約に従う）。
    return os.environ.get("SYNAPSE_MEMORY_DIR") or os.path.expanduser(
        "~/.claude/brain-memory/synapse")


def read_connectome(scope="default", base_dir=None):
    """synapse の connectome snapshot を読み取る（read-only・派生物）。無ければ None。"""
    base = base_dir or _synapse_memory_dir()
    fn = "connectome.json" if scope in (None, "default") else "connectome-%s.json" % scope
    return secure_io.read_json(os.path.join(base, fn))


def record_coactivation(skills, outcome="unverified", scope="default", base_dir=None):
    """共起を synapse へ記録する（best-effort）。委譲先が無ければ False を返す。

    本体の event log とは独立。synapse の append-only ログに委譲することで、
    関係の重み育成・忘却・剪定を再利用する。
    """
    if not available() or not skills:
        return False
    scripts = os.path.join(synapse_skill_dir(), "scripts")
    env = dict(os.environ)
    if base_dir:
        env["SYNAPSE_MEMORY_DIR"] = base_dir
    try:
        subprocess.run(
            [sys.executable, "-m", "synapse", "observe",
             "--skills", ",".join(skills), "--outcome", outcome, "--scope", scope],
            cwd=scripts, env=env, timeout=20,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def status():
    return {"available": available(), "skill_dir": synapse_skill_dir(),
            "memory_dir": _synapse_memory_dir(),
            "role": "関係学習・可塑性・忘却（relation graph）を委譲する再利用モジュール"}

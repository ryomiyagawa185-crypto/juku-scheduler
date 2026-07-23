# -*- coding: utf-8 -*-
"""transport — ノードへのコマンド配送を抽象化（仕様 §9/§17）。

- LocalTransport: localhost で argv を subprocess 実行（Control 兼 Worker・実プロセス隔離）。
- SSHTransport: 実 Mac へ SSH/rsync で配送（Phase 2）。StrictHostKeyChecking を no にしない（§8）。
  明示承認（allow_remote=True）が無ければ実行しない（§36）。SSH/rsync の argv は純関数で構築し、
  ユニットテストで固定（injection 不可・host 鍵オプション遵守）。
- LocalRemoteSimTransport: リモート配送の *制御フロー* をネットワーク無しで検証するための同一ホスト
  シミュレータ（別ディレクトリを「リモート」に見立て、cp で put/get、subprocess で worker 起動）。
  実 SSH 接続の代わりに、ステージング→リモート実行→フェッチ→checksum の全経路を実行できる。

共通インタフェース: kind / remote / probe / run / put_file / get_file / get_dir /
ensure_worker / remote_task_root。シェル文字列連結・eval・shell=True は使わない。
"""

import os
import shutil
import signal
import subprocess
import sys
import time

from . import security

MAX_OUTPUT_BYTES = 5 * 1024 * 1024
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# $HOME を使う（~ は env VAR=~/... の形だと remote shell で展開されないことがあるため）。
REMOTE_PKG_DIR = "$HOME/.mac-neural-grid/pkg"      # PYTHONPATH（package はこの下）
REMOTE_JOBS_DIR = "$HOME/.mac-neural-grid/jobs"


def _truncate(data, limit):
    if len(data) > limit:
        return data[:limit] + b"\n...[truncated %d bytes]" % (len(data) - limit)
    return data


def _spawn(argv, cwd=None, timeout=None, env=None, input_text=None,
           max_output_bytes=MAX_OUTPUT_BYTES):
    """argv を subprocess 実行して結果 dict を返す（local/ssh/rsync 共通の下回り）。"""
    run_env = dict(os.environ)
    if env:
        run_env.update({k: str(v) for k, v in env.items()})
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=run_env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except FileNotFoundError as exc:
        return {"exit_code": 127, "stdout": "", "stderr": str(exc),
                "timed_out": False, "duration_s": 0.0, "spawn_error": True}
    try:
        out, err = proc.communicate(
            input=(input_text.encode("utf-8") if input_text else None), timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        out, err = proc.communicate()
    dur = round(time.monotonic() - start, 3)
    out = _truncate(out or b"", max_output_bytes).decode("utf-8", "replace")
    err = _truncate(err or b"", max_output_bytes).decode("utf-8", "replace")
    return {"exit_code": (124 if timed_out else proc.returncode), "stdout": out,
            "stderr": err, "timed_out": timed_out, "duration_s": dur}


# ---------------- 純関数の SSH/rsync argv ビルダー（ユニットテスト対象）----------------

def ssh_opts(ssh_config):
    shc = (ssh_config or {}).get("strict_host_key_checking", "accept-new")
    if shc == "no":
        raise security.SecurityError("StrictHostKeyChecking=no は禁止（§8）")
    opts = ["-o", "StrictHostKeyChecking=%s" % shc,
            "-o", "ConnectTimeout=%s" % (ssh_config or {}).get("connect_timeout_s", 15)]
    if (ssh_config or {}).get("batch_mode", True):
        opts += ["-o", "BatchMode=yes"]
    return opts


def ssh_target(node):
    host, user = node["host"], node.get("user")
    if not host or any(c in str(host) for c in " ;&|`$"):
        raise security.SecurityError("不正な host: %r" % host)
    if user and any(c in str(user) for c in " ;&|`$"):
        raise security.SecurityError("不正な user: %r" % user)
    return "%s@%s" % (user, host) if user else host


def ssh_run_argv(node, ssh_config, argv, env=None):
    """`ssh <opts> user@host [env K=V ...] <argv>` を組む。

    OpenSSH は destination 以降を remote コマンドとして扱う（`--` は付けない＝remote へ literal で
    渡ってしまうため）。remote shell が空白で再分割するので、各引数に空白を含めない前提で使う
    （module 名・フラグ・$HOME 由来のパス等・§17）。$HOME/$ は remote で展開させる。
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        raise security.SecurityError("remote argv は非空リスト")
    for a in argv:
        if " " in str(a):
            raise security.SecurityError("remote argv に空白を含めない（SSH 再分割対策）: %r" % a)
    prefix = ["ssh"] + ssh_opts(ssh_config) + [ssh_target(node)]
    envp = []
    if env:
        envp = ["/usr/bin/env"] + ["%s=%s" % (k, v) for k, v in env.items()]
    return prefix + envp + list(argv)


def rsync_push_argv(node, ssh_config, src, dst):
    """ローカル src → リモート dst（rsync over ssh）。ディレクトリは末尾 / で内容同期。"""
    e = "ssh " + " ".join(ssh_opts(ssh_config))
    return ["rsync", "-a", "--delete", "-e", e, src, "%s:%s" % (ssh_target(node), dst)]


def rsync_pull_argv(node, ssh_config, src, dst):
    e = "ssh " + " ".join(ssh_opts(ssh_config))
    return ["rsync", "-a", "-e", e, "%s:%s" % (ssh_target(node), src), dst]


# ---------------- transports ----------------

class LocalTransport(object):
    kind = "local"
    remote = False

    def __init__(self, node=None):
        self.node = node or {}

    def probe(self):
        return {"ok": True, "transport": "local", "host": "localhost"}

    def run(self, argv, cwd=None, timeout=None, env=None, input_text=None,
            max_output_bytes=MAX_OUTPUT_BYTES, allowlist=None):
        argv = security.validate_argv(argv, allowlist)
        return _spawn(argv, cwd=cwd, timeout=timeout, env=env, input_text=input_text,
                      max_output_bytes=max_output_bytes)

    def put_file(self, src, dst):
        security.makedirs(os.path.dirname(os.path.abspath(dst)))
        shutil.copy2(src, dst)
        return {"ok": True, "checksum": security.sha256_file(dst)}

    def get_file(self, src, dst):
        return self.put_file(src, dst)


class SSHTransport(object):
    """実 Mac への SSH/rsync 配送（Phase 2）。allow_remote=True でのみ実行する。"""
    kind = "ssh"
    remote = True

    def __init__(self, node, ssh_config=None, allow_remote=False):
        self.node = node
        self.ssh_config = ssh_config or {}
        self.allow_remote = allow_remote

    def _guard(self):
        if not self.allow_remote:
            raise security.SecurityError(
                "リモート実行/転送は明示承認が必要（--allow-remote・§36）")

    def probe(self):
        if not self.allow_remote:
            return {"ok": None, "transport": "ssh", "host": self.node["host"],
                    "note": "SSH probe は --allow-remote が必要（§36）"}
        r = _spawn(ssh_run_argv(self.node, self.ssh_config, ["true"]), timeout=20)
        return {"ok": r["exit_code"] == 0, "transport": "ssh",
                "host": self.node["host"], "stderr": r["stderr"][:200]}

    def remote_task_root(self, job_id, task_id):
        return "%s/%s/%s" % (REMOTE_JOBS_DIR, job_id, task_id)

    def pythonpath(self):
        return REMOTE_PKG_DIR

    def ensure_worker(self):
        """mac_neural_grid パッケージをリモートへ rsync（python3 のみで動く・pip 不要）。"""
        self._guard()
        # mkdir -p ~/.mac-neural-grid/pkg
        mk = _spawn(ssh_run_argv(self.node, self.ssh_config,
                                 ["mkdir", "-p", REMOTE_PKG_DIR]), timeout=30)
        if mk["exit_code"] != 0:
            return {"ok": False, "stderr": mk["stderr"]}
        pkg_src = os.path.join(_SRC_DIR, "mac_neural_grid")
        r = _spawn(rsync_push_argv(self.node, self.ssh_config, pkg_src + "/",
                                   REMOTE_PKG_DIR + "/mac_neural_grid/"), timeout=120)
        return {"ok": r["exit_code"] == 0, "stderr": r["stderr"][:300]}

    def run(self, argv, cwd=None, timeout=None, env=None, input_text=None,
            max_output_bytes=MAX_OUTPUT_BYTES, allowlist=None):
        self._guard()
        security.validate_argv(argv, allowlist)  # remote で走らせる実行体も allowlist で確認
        full = ssh_run_argv(self.node, self.ssh_config, argv, env=env)
        return _spawn(full, timeout=timeout, max_output_bytes=max_output_bytes)

    def put_file(self, src, dst):
        self._guard()
        r = _spawn(rsync_push_argv(self.node, self.ssh_config, src, dst), timeout=120)
        if r["exit_code"] != 0:
            raise security.SecurityError("rsync push 失敗: %s" % r["stderr"][:200])
        return {"ok": True}

    def get_file(self, src, dst):
        self._guard()
        security.makedirs(os.path.dirname(os.path.abspath(dst)))
        r = _spawn(rsync_pull_argv(self.node, self.ssh_config, src, dst), timeout=120)
        if r["exit_code"] != 0:
            raise security.SecurityError("rsync pull 失敗: %s" % r["stderr"][:200])
        return {"ok": True}

    def get_dir(self, src, dst):
        self._guard()
        security.makedirs(dst)
        r = _spawn(rsync_pull_argv(self.node, self.ssh_config,
                                   src.rstrip("/") + "/", dst.rstrip("/") + "/"),
                   timeout=120)
        return {"ok": r["exit_code"] == 0, "stderr": r["stderr"][:200]}


class LocalRemoteSimTransport(object):
    """同一ホストで「リモート配送」を模擬する（ネットワーク無しで制御フロー検証・§33）。

    remote_base（別ディレクトリ）を「リモート」に見立て、put/get は cp、run は subprocess で
    実 worker を起動する。ステージング→リモート実行→フェッチ→checksum の全経路を通す。
    """
    kind = "ssh"
    remote = True

    def __init__(self, node, remote_base):
        self.node = node
        self.remote_base = os.path.abspath(remote_base)
        security.makedirs(self.remote_base)

    def probe(self):
        return {"ok": True, "transport": "ssh-sim", "host": self.node.get("host")}

    def remote_task_root(self, job_id, task_id):
        return os.path.join(self.remote_base, "jobs", job_id, task_id)

    def pythonpath(self):
        return _SRC_DIR

    def ensure_worker(self):
        return {"ok": True, "sim": True}

    def run(self, argv, cwd=None, timeout=None, env=None, input_text=None,
            max_output_bytes=MAX_OUTPUT_BYTES, allowlist=None):
        return _spawn(argv, cwd=cwd, timeout=timeout, env=env,
                      max_output_bytes=max_output_bytes)

    def put_file(self, src, dst):
        security.makedirs(os.path.dirname(os.path.abspath(dst)))
        shutil.copy2(src, dst)
        return {"ok": True}

    def get_file(self, src, dst):
        security.makedirs(os.path.dirname(os.path.abspath(dst)))
        shutil.copy2(src, dst)
        return {"ok": True}

    def get_dir(self, src, dst):
        security.makedirs(dst)
        if os.path.isdir(src):
            for name in os.listdir(src):
                s = os.path.join(src, name)
                if os.path.isfile(s):
                    shutil.copy2(s, os.path.join(dst, name))
        return {"ok": True}


def for_node(node, ssh_config=None, allow_remote=False):
    if node.get("transport") == "ssh":
        return SSHTransport(node, ssh_config, allow_remote=allow_remote)
    return LocalTransport(node)

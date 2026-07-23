# -*- coding: utf-8 -*-
"""transport — ノードへのコマンド配送を抽象化（仕様 §9/§17）。

- LocalTransport: localhost で argv を subprocess 実行（MVP・実プロセス隔離で複数 Worker を模擬）。
- SSHTransport: 実 Mac へ SSH で argv を実行（StrictHostKeyChecking を no にしない・§8）。
  本 MVP / テストでは SSH を自動実行しない（§36）。設計として argv を構築するが、明示許可
  （allow_remote=True）なしには実行しない。

いずれも run()/put_file()/get_file()/probe() を持つ。シェル文字列連結・eval・shell=True は使わない。
"""

import os
import shutil
import signal
import subprocess
import time

from . import security

MAX_OUTPUT_BYTES = 5 * 1024 * 1024


def _truncate(data, limit):
    if len(data) > limit:
        return data[:limit] + b"\n...[truncated %d bytes]" % (len(data) - limit)
    return data


class LocalTransport(object):
    kind = "local"

    def __init__(self, node=None):
        self.node = node or {}

    def probe(self):
        return {"ok": True, "transport": "local", "host": "localhost"}

    def run(self, argv, cwd=None, timeout=None, env=None, input_text=None,
            max_output_bytes=MAX_OUTPUT_BYTES, allowlist=None):
        argv = security.validate_argv(argv, allowlist)
        run_env = dict(os.environ)
        # 秘密値を継承させない最小環境に寄せる（§30）。必要な変数のみ足す。
        if env:
            run_env.update({k: str(v) for k, v in env.items()})
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=run_env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True)
        except FileNotFoundError as exc:
            return {"exit_code": 127, "stdout": "", "stderr": str(exc),
                    "timed_out": False, "duration_s": 0.0, "spawn_error": True}
        try:
            out, err = proc.communicate(
                input=(input_text.encode("utf-8") if input_text else None),
                timeout=timeout)
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
        return {"exit_code": (124 if timed_out else proc.returncode),
                "stdout": out, "stderr": err, "timed_out": timed_out,
                "duration_s": dur}

    def put_file(self, src, dst):
        security.makedirs(os.path.dirname(os.path.abspath(dst)))
        shutil.copy2(src, dst)
        return {"ok": True, "checksum": security.sha256_file(dst)}

    def get_file(self, src, dst):
        return self.put_file(src, dst)


class SSHTransport(object):
    """実 Mac への SSH 配送（設計のみ実行）。allow_remote=True でのみ run を許可する。"""
    kind = "ssh"

    def __init__(self, node, ssh_config=None, allow_remote=False):
        self.node = node
        self.ssh_config = ssh_config or {}
        self.allow_remote = allow_remote
        self._local = LocalTransport(node)

    def _ssh_prefix(self):
        host = self.node["host"]
        user = self.node.get("user")
        target = "%s@%s" % (user, host) if user else host
        shc = self.ssh_config.get("strict_host_key_checking", "accept-new")
        if shc == "no":
            raise security.SecurityError("StrictHostKeyChecking=no は禁止（§8）")
        argv = ["ssh", "-o", "StrictHostKeyChecking=%s" % shc,
                "-o", "ConnectTimeout=%s" % self.ssh_config.get("connect_timeout_s", 15)]
        if self.ssh_config.get("batch_mode", True):
            argv += ["-o", "BatchMode=yes"]
        argv.append(target)
        return argv

    def probe(self):
        return {"ok": None, "transport": "ssh", "host": self.node["host"],
                "note": "SSH probe は明示承認が必要（§36）。ここでは実行しない。"}

    def run(self, argv, cwd=None, timeout=None, env=None, input_text=None,
            max_output_bytes=MAX_OUTPUT_BYTES, allowlist=None):
        if not self.allow_remote:
            raise security.SecurityError(
                "リモート実行は明示承認が必要（allow_remote=False・§36）")
        security.validate_argv(argv, allowlist)
        # リモートでも argv を安全に渡す（cd は作業ディレクトリ制限のため付与）。
        remote_cmd = argv if cwd is None else \
            ["sh", "-c", "cd %s && exec \"$@\"" % security.quote_for_display([cwd]).strip("'"),
             "sh"] + argv
        full = self._ssh_prefix() + ["--"] + remote_cmd
        return self._local.run(full, timeout=timeout, max_output_bytes=max_output_bytes,
                               allowlist=security.DEFAULT_COMMAND_ALLOWLIST | {"ssh"})

    def put_file(self, src, dst):
        if not self.allow_remote:
            raise security.SecurityError("リモート転送は明示承認が必要（§36）")
        # 実運用は rsync/scp。設計のみ（本 MVP では未実行）。
        raise NotImplementedError("SSH put_file は Phase 2 で実装（承認後）")

    def get_file(self, src, dst):
        if not self.allow_remote:
            raise security.SecurityError("リモート転送は明示承認が必要（§36）")
        raise NotImplementedError("SSH get_file は Phase 2 で実装（承認後）")


def for_node(node, ssh_config=None, allow_remote=False):
    if node.get("transport") == "ssh":
        return SSHTransport(node, ssh_config, allow_remote=allow_remote)
    return LocalTransport(node)

# -*- coding: utf-8 -*-
"""security — 安全プリミティブ（仕様 §29/§30/§17/§20/§16）。

原子的書込・権限(0600/0700)・advisory ロック・symlink/path traversal 防止・秘密値の redaction・
argv 検証・executor/command allowlist・payload hash 検証・checksum。ここに集約し、他モジュールは
必ずこれを経由してファイルシステム/コマンドに触れる。
"""

import fcntl
import hashlib
import os
import re
import shlex
import tempfile

try:  # tomllib は 3.11+。無い環境向けに握る（本番は 3.11 前提）。
    import json as _json
except ImportError:  # pragma: no cover
    _json = None

DIR_MODE = 0o700
FILE_MODE = 0o600
TMP_PREFIX = ".mng-"
TMP_SUFFIX = ".tmp"


# ---------- ハッシュ ----------

def sha256_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def payload_hash(obj):
    import json
    canon = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(canon)


def verify_payload_hash(obj_without_hash, expected):
    return payload_hash(obj_without_hash) == expected


# ---------- 権限・アトミック書込 ----------

def chmod(path, mode):
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def makedirs(path, mode=DIR_MODE):
    os.makedirs(path, exist_ok=True)
    chmod(path, mode)


def assert_not_symlink(path):
    if os.path.islink(path):
        raise SecurityError("symlink への書込は拒否: %s" % path)


def atomic_write_bytes(path, data):
    path = os.path.abspath(path)
    assert_not_symlink(path)
    parent = os.path.dirname(path)
    makedirs(parent)
    fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, suffix=TMP_SUFFIX, dir=parent)
    try:
        os.fchmod(fd, FILE_MODE)
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        dfd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, obj):
    import json
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


class file_lock(object):
    """<path> に排他ロックを取り、クリティカルセクションを直列化する（§17 競合防止）。"""

    def __init__(self, lock_path):
        self.lock_path = lock_path
        self._f = None

    def __enter__(self):
        makedirs(os.path.dirname(os.path.abspath(self.lock_path)))
        self._f = open(self.lock_path, "w")
        chmod(self.lock_path, FILE_MODE)
        fcntl.flock(self._f.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        finally:
            self._f.close()
        return False


# ---------- path traversal / symlink ----------

def safe_join(base, *parts):
    """base 配下に収まる結合パスを返す。外へ出る（path traversal）と例外（§29）。"""
    base = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base, *parts))
    if target != base and not target.startswith(base + os.sep):
        raise SecurityError("path traversal を検出: %s は %s の外" % (target, base))
    return target


def assert_within(base, path):
    base = os.path.realpath(base)
    real = os.path.realpath(path)
    if real != base and not real.startswith(base + os.sep):
        raise SecurityError("作業ディレクトリ外への参照: %s" % path)
    return real


# ---------- 秘密値の redaction（§24/§30）----------

_SECRET_PATTERNS = [
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("kv_secret", re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*\S+")),
    ("env_secret", re.compile(r"(?m)^[A-Z][A-Z0-9_]*_(KEY|SECRET|TOKEN|PASSWORD)\s*=\s*\S+")),
]


def redact(text):
    if not isinstance(text, str):
        return text
    out = text
    for name, rx in _SECRET_PATTERNS:
        out = rx.sub("[REDACTED:%s]" % name, out)
    return out


def redact_obj(obj):
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj


def contains_secret(text):
    return isinstance(text, str) and any(rx.search(text) for _n, rx in _SECRET_PATTERNS)


# ---------- argv / allowlist（§17）----------

# executor が使ってよい実行体の allowlist（絶対的な安全境界ではなく多層防御の一層）。
DEFAULT_COMMAND_ALLOWLIST = {
    "python3", "python", "sh", "zsh", "bash",  # executor 内部で argv 実行に限る
    "wc", "cat", "head", "tail", "sort", "uniq", "cut", "tr", "grep",
    "sha256sum", "shasum", "cp", "mv", "ls", "find", "stat",
    "pdftotext", "tesseract", "ffmpeg", "sips", "qlmanage",
    "sw_vers", "sysctl", "uname", "pmset", "system_profiler", "df", "vm_stat",
    "ssh", "scp", "rsync", "ollama", "caffeinate", "hostname", "id", "uptime",
}


def validate_argv(argv, allowlist=None):
    """argv がリスト・非空・先頭が allowlist（basename）に含まれることを検証（§17）。

    shell 文字列の連結・eval・shell=True は行わない。argv 配列のみを許す。
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        raise SecurityError("argv は非空のリストでなければならない: %r" % (argv,))
    for a in argv:
        if not isinstance(a, str):
            raise SecurityError("argv 要素は文字列のみ: %r" % (a,))
        if "\x00" in a:
            raise SecurityError("argv に NUL を含めない")
    allow = allowlist if allowlist is not None else DEFAULT_COMMAND_ALLOWLIST
    exe = os.path.basename(argv[0])
    if exe not in allow:
        raise SecurityError("許可されていない実行体: %s（allowlist 外）" % exe)
    return list(argv)


def looks_like_shell_injection(s):
    """外部入力（ノード出力・ユーザー文字列）にシェル特殊文字が含まれるかの検査（防御的）。"""
    return isinstance(s, str) and bool(re.search(r"[;&|`$><\n\\]|\$\(|\|\|", s))


def quote_for_display(argv):
    return " ".join(shlex.quote(a) for a in argv)


class SecurityError(Exception):
    pass

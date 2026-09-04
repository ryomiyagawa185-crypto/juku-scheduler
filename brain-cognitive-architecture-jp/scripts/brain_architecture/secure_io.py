# -*- coding: utf-8 -*-
"""secure_io — 安全なアトミック書込・権限・advisory ロック・backup+checksum（仕様 §16）。

同一ディレクトリ内のランダム一時ファイルへ書き、fchmod(0600)→fsync→os.replace→
親dir fsync の順でアトミックに差し替える（symlink 差し替え・path traversal・中断復旧に
強い）。verify/ dry-run は本モジュールの書込 API を一切呼ばない（読取専用を保証）。
"""

import fcntl
import hashlib
import json
import os
import tempfile

DIR_MODE = 0o700
FILE_MODE = 0o600
TMP_PREFIX = ".brain-"
TMP_SUFFIX = ".tmp"


def chmod(path, mode):
    """best-effort chmod（一部FSでは無視されうるので失敗は握る）。"""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def makedirs(path, mode=DIR_MODE):
    os.makedirs(path, exist_ok=True)
    chmod(path, mode)


def sha256_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256_bytes(text.encode("utf-8"))


def _assert_not_symlink(path):
    """既存ターゲットが symlink なら拒否（symlink 追随書込を防ぐ・§16）。"""
    if os.path.islink(path):
        raise OSError("symlink への書込は拒否: %s" % path)


def atomic_write_bytes(path, data):
    """バイト列を安全にアトミック書込する。"""
    path = os.path.abspath(path)
    _assert_not_symlink(path)
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
        dir_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2,
                                  sort_keys=False) + "\n")


def append_jsonl(path, obj):
    """append-only ログへ1行追記（イベントログ用）。fsync して 0600 に寄せる。"""
    path = os.path.abspath(path)
    _assert_not_symlink(path)
    parent = os.path.dirname(path)
    makedirs(parent)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    chmod(path, FILE_MODE)


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json(path, default=None):
    """壊れた JSON でも例外にせず default を返す（§18 壊れたJSON耐性）。"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return default


def backup_file(path, backups_dir, label="backup"):
    """既存ファイルを backups_dir へ退避し、.sha256 を併記する（rollback 用・§16）。

    戻り値: (backup_path, sha256) または (None, None)（元ファイルが無い場合）。
    """
    if not os.path.exists(path):
        return None, None
    makedirs(backups_dir)
    data = open(path, "rb").read()
    digest = sha256_bytes(data)
    base = os.path.basename(path)
    # 決定的名（時刻に依存しない）: label + content hash 先頭。
    name = "%s.%s.%s.bak" % (base, label, digest.split(":")[1][:16])
    dst = os.path.join(backups_dir, name)
    atomic_write_bytes(dst, data)
    atomic_write(dst + ".sha256", digest + "  " + base + "\n")
    return dst, digest


def upsert_line_prepend(path, key, line):
    """newest-first 台帳で、同一 key の既存行を除いてから先頭へ差し込む（冪等）。"""
    marker = "<!-- k:%s -->" % key
    full = line.rstrip("\n") + " " + marker + "\n"
    old = read_text(path) if os.path.exists(path) else ""
    kept = [ln for ln in old.splitlines() if marker not in ln]
    tail = ("\n".join(kept) + "\n") if kept else ""
    atomic_write(path, full + tail)


class file_lock(object):
    """<dir>/.lock に排他ロックを取り、クリティカルセクションを直列化する（§16 競合書込）。"""

    def __init__(self, base_dir, lock_path):
        self.base = base_dir
        self.lock_path = lock_path
        self._f = None

    def __enter__(self):
        makedirs(self.base)
        self._f = open(self.lock_path, "w", encoding="utf-8")
        chmod(self.lock_path, FILE_MODE)
        fcntl.flock(self._f.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        finally:
            self._f.close()
        return False

# -*- coding: utf-8 -*-
"""artifact_store — 成果物の登録と安全な転送（仕様 §20）。

手順: 一時名で転送 → checksum 確認 → 原子的に正式名へ改名。空き容量・サイズ・同名上書き・
転送途中の中断・機密性を確認する。ノードからの成果物も未信頼として扱い、サイズと checksum を検証。
"""

import os
import shutil

from . import security


def free_disk_gb(path):
    try:
        return shutil.disk_usage(os.path.dirname(os.path.abspath(path)) or "/").free \
            / (1024 ** 3)
    except OSError:
        return None


def transfer(src, dst, expected_checksum=None, max_bytes=None):
    """一時名で転送 → checksum 確認 → os.replace で原子的に確定（§20）。

    戻り値: {ok, checksum, size_bytes}。checksum 不一致や容量不足は例外。
    """
    if not os.path.exists(src):
        raise FileNotFoundError("転送元が無い: %s" % src)
    size = os.path.getsize(src)
    if max_bytes is not None and size > max_bytes:
        raise ValueError("成果物が上限超過: %d > %d" % (size, max_bytes))
    free = free_disk_gb(dst)
    if free is not None and size / (1024 ** 3) > free:
        raise OSError("空き容量不足: 必要 %.2fGB / 空き %.2fGB" % (size / (1024 ** 3), free))
    security.makedirs(os.path.dirname(os.path.abspath(dst)))
    tmp = dst + security.TMP_SUFFIX
    security.assert_not_symlink(dst)
    shutil.copy2(src, tmp)
    checksum = security.sha256_file(tmp)
    if expected_checksum and checksum != expected_checksum:
        os.unlink(tmp)
        raise ValueError("checksum 不一致（破損/改竄の疑い）: %s != %s"
                         % (checksum, expected_checksum))
    os.replace(tmp, dst)   # 原子的確定
    security.chmod(dst, security.FILE_MODE)
    return {"ok": True, "checksum": checksum, "size_bytes": size}


def collect(db, task_id, output_dir, central_dir=None, manifest=None):
    """タスク output/ の成果物を検証して DB に登録し、任意で中央 artifacts へ集約する。"""
    registered = []
    manifest_checks = {a["name"]: a.get("checksum")
                       for a in (manifest or {}).get("artifacts", [])}
    if not os.path.isdir(output_dir):
        return registered
    for name in sorted(os.listdir(output_dir)):
        src = security.safe_join(output_dir, name)
        if not os.path.isfile(src):
            continue
        checksum = security.sha256_file(src)
        expected = manifest_checks.get(name)
        if expected and expected != checksum:
            raise ValueError("成果物 checksum 不一致: %s (%s != %s)"
                             % (name, checksum, expected))
        size = os.path.getsize(src)
        dst = src
        if central_dir:
            dst = security.safe_join(central_dir, task_id + "__" + name)
            transfer(src, dst, expected_checksum=checksum)
        aid = "art-" + checksum.split(":")[1][:16]
        db.add_artifact(aid, task_id, dst, checksum, size)
        registered.append({"artifact_id": aid, "name": name, "checksum": checksum,
                           "size_bytes": size, "path": dst})
    return registered

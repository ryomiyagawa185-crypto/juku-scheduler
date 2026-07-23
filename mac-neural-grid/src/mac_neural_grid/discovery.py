# -*- coding: utf-8 -*-
"""discovery — ノード能力の調査（仕様 §7）。環境を固定仮定せず、調べて能力台帳を作る。

自動発見（mDNS 等）は既定で無効（§8 安全な手動登録優先）。inspect は読取専用。
macOS 重視で情報を集めつつ、他 OS では graceful degradation する（null を許容）。localhost は
Python 標準ライブラリで確実に収集し、リモート Mac は inspect-node.zsh を SSH 経由で実行する設計
（Phase 2・本 MVP では未実行）。
"""

import os
import platform
import shutil

from .database import now_iso

# ノードで探す代表的ツール（capability 台帳・§7）。
_TOOL_PROBES = {
    "claude_code": "claude", "ollama": "ollama", "ffmpeg": "ffmpeg",
    "pdftotext": "pdftotext", "tesseract": "tesseract", "python3": "python3",
    "brew": "brew", "git": "git", "rsync": "rsync", "sips": "sips",
    "caffeinate": "caffeinate", "qlmanage": "qlmanage",
}


def _mem_gb():
    try:
        if platform.system() == "Darwin":
            return None  # remote/darwin は sysctl 経由（zsh スクリプト）。local darwin は下で補完。
        # Linux: /proc/meminfo
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / (1024 * 1024), 1)
    except OSError:
        return None
    return None


def _mem_gb_local():
    # local ノードは sysconf でメモリ量を取得（darwin/linux 共通）。
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page / (1024 ** 3), 1)
    except (ValueError, OSError, AttributeError):
        return _mem_gb()


def _free_disk_gb(path="/"):
    try:
        return round(shutil.disk_usage(path).free / (1024 ** 3), 1)
    except OSError:
        return None


def _neural_engine(arch):
    # Apple Silicon は Neural Engine を持つ（arm64 macOS）。数値融合は主張しない。
    if arch == "arm64" and platform.system() == "Darwin":
        return "Apple Neural Engine (arm64)"
    return None


def inspect_local(node_id="localhost"):
    """localhost の能力を読取専用で収集する（クロスプラットフォーム）。"""
    arch = platform.machine()
    tools = {name: bool(shutil.which(cmd)) for name, cmd in _TOOL_PROBES.items()}
    models = _ollama_models() if tools.get("ollama") else []
    try:
        load1 = os.getloadavg()[0]
        cores = os.cpu_count() or 1
        cpu_percent = round(min(100.0, 100.0 * load1 / cores), 1)
    except (OSError, AttributeError):
        cpu_percent = None
    return {
        "node_id": node_id,
        "collected_at": now_iso(),
        "os_version": _os_version(),
        "architecture": arch,
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores": os.cpu_count(),
        "memory_gb": _mem_gb_local(),
        "free_disk_gb": _free_disk_gb(),
        "gpu": _neural_engine(arch),
        "power_source": _power_source(),
        "battery_percent": None,
        "thermal_state": None,
        "tools": tools,
        "models": models,
        "current_load": {"cpu_percent": cpu_percent, "active_jobs": 0},
    }


def _os_version():
    if platform.system() == "Darwin":
        return "macOS %s" % platform.mac_ver()[0]
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "%s %s" % (platform.system(), platform.release())


def _power_source():
    # macOS は pmset、Linux は /sys で判定。取得不能は null（固定仮定しない）。
    try:
        if platform.system() == "Linux":
            base = "/sys/class/power_supply"
            if os.path.isdir(base):
                for name in os.listdir(base):
                    t = os.path.join(base, name, "type")
                    if os.path.exists(t) and open(t).read().strip() == "Mains":
                        online = os.path.join(base, name, "online")
                        if os.path.exists(online):
                            return "AC" if open(online).read().strip() == "1" else "battery"
    except OSError:
        return None
    return None


def _ollama_models():
    try:
        from .transport import LocalTransport
        r = LocalTransport().run(["ollama", "list"], timeout=10)
        if r["exit_code"] == 0:
            return [ln.split()[0] for ln in r["stdout"].splitlines()[1:] if ln.strip()]
    except Exception:  # noqa: BLE001
        return []
    return []


def inspect_remote(node, ssh_config=None):
    """リモート Mac の能力を SSH 経由で収集する（Phase 2・要 allow_remote）。

    リモートへ配備した package の同じ inspect_local を `python3 -m mac_neural_grid.discovery`
    として実行し JSON を得る（空白の無い引数のみ＝SSH 再分割に安全）。python3 が無いリモートは
    scripts/inspect-node.zsh を代替に使える（別途）。
    """
    from .transport import SSHTransport
    import json
    t = SSHTransport(node, ssh_config, allow_remote=True)
    ew = t.ensure_worker()
    if not ew.get("ok"):
        return {"node_id": node.get("node_id"), "collected_at": now_iso(),
                "tools": {}, "models": [], "error": "worker 配備に失敗: %s" % ew.get("stderr")}
    r = t.run(["python3", "-m", "mac_neural_grid.discovery", node["node_id"]],
              env={"PYTHONPATH": t.pythonpath()}, timeout=30)
    if r["exit_code"] != 0:
        return {"node_id": node.get("node_id"), "collected_at": now_iso(),
                "tools": {}, "models": [], "error": "remote inspect 失敗: %s" % r["stderr"][:200]}
    for line in reversed((r["stdout"] or "").strip().splitlines()):
        try:
            data = json.loads(line)
            if isinstance(data, dict) and data.get("node_id"):
                return data
        except ValueError:
            continue
    return {"node_id": node.get("node_id"), "collected_at": now_iso(),
            "tools": {}, "models": [], "error": "remote inspect の JSON 解析に失敗"}


def inspect_node(node, allow_remote=False, ssh_config=None):
    """node の transport に応じて能力を収集する。ssh は allow_remote=True の時のみ実接続（§36）。"""
    if node.get("transport") in (None, "local") or node.get("host") in ("localhost",
                                                                         "127.0.0.1"):
        return inspect_local(node.get("node_id", "localhost"))
    if allow_remote:
        return inspect_remote(node, ssh_config)
    return {"node_id": node.get("node_id"), "collected_at": now_iso(),
            "architecture": None, "tools": {}, "models": [],
            "note": "リモート inspect は --allow-remote が必要（§36）"}


if __name__ == "__main__":  # remote 実行用（python3 -m mac_neural_grid.discovery <node_id>）
    import json as _json
    import sys as _sys
    _nid = _sys.argv[1] if len(_sys.argv) > 1 else "remote"
    print(_json.dumps(inspect_local(_nid), ensure_ascii=False))

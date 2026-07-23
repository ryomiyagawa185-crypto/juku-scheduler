# -*- coding: utf-8 -*-
"""inventory — ノード台帳の操作（仕様 §7/§8/§29）。

安全な手動登録を優先（自動発見は既定で無効）。登録時に host 鍵・ユーザー・実体・アーキ・ツール・
作業ディレクトリ・信頼レベルを確認する。StrictHostKeyChecking=no を既定にしない。
"""

from . import ids, schemas, discovery
from .database import now_iso


def add_node(db, host, user=None, name=None, transport=None, labels=None,
             work_root=None, trust="medium", host_key_fingerprint=None, actor="cli"):
    """ノードを登録する。localhost は transport=local、リモートは ssh（host 鍵確認が前提）。"""
    is_local = host in ("localhost", "127.0.0.1", None)
    transport = transport or ("local" if is_local else "ssh")
    name = name or (host if not is_local else "localhost")
    if transport == "ssh" and not host_key_fingerprint:
        # host 鍵未確認のリモートは untrusted で登録し、node trust/inspect を促す（§8）。
        trust = "untrusted"
    node = {
        "node_id": ids.node_id(name, host or "localhost"),
        "display_name": name, "host": host or "localhost", "user": user,
        "transport": transport, "trust": trust, "labels": labels or [],
        "work_root": work_root, "enabled": True,
        "host_key_fingerprint": host_key_fingerprint, "added_at": now_iso(),
    }
    errors = schemas.validate(node, schemas.NODE_SCHEMA)
    if errors:
        raise ValueError("node schema 違反: %s" % "; ".join(errors))
    db.upsert_node(node)
    db.append_event("node_added", data={"node_id": node["node_id"], "transport": transport})
    db.audit(actor, "node_add", {"node_id": node["node_id"], "host": host,
                                 "transport": transport, "trust": trust})
    return node


def inspect(db, node_id, actor="cli"):
    """ノードを調査して能力台帳を更新する（読取専用の調査）。"""
    node = db.get_node(node_id)
    if node is None:
        raise KeyError("node が無い: %s" % node_id)
    cap = discovery.inspect_node(node)
    errors = schemas.validate(cap, schemas.CAPABILITY_SCHEMA)
    if errors:
        raise ValueError("capability schema 違反: %s" % "; ".join(errors))
    db.set_capabilities(node_id, cap)
    db.conn.execute("UPDATE nodes SET last_heartbeat=? WHERE node_id=?",
                    (now_iso(), node_id))
    db.audit(actor, "node_inspect", {"node_id": node_id})
    return cap


def set_trust(db, node_id, level, actor="cli"):
    if level not in schemas.TRUST_LEVELS:
        raise ValueError("不正な trust: %s" % level)
    node = db.get_node(node_id)
    if node is None:
        raise KeyError("node が無い: %s" % node_id)
    node["trust"] = level
    db.upsert_node(node)
    db.audit(actor, "node_trust", {"node_id": node_id, "trust": level})
    return node


def set_enabled(db, node_id, enabled, actor="cli"):
    node = db.get_node(node_id)
    if node is None:
        raise KeyError("node が無い: %s" % node_id)
    node["enabled"] = bool(enabled)
    db.upsert_node(node)
    db.audit(actor, "node_disable" if not enabled else "node_enable", {"node_id": node_id})
    return node


def remove_node(db, node_id, actor="cli"):
    db.remove_node(node_id)
    db.audit(actor, "node_remove", {"node_id": node_id})


def ping(db, node_id, config=None):
    from .transport import for_node
    node = db.get_node(node_id)
    if node is None:
        raise KeyError("node が無い: %s" % node_id)
    return for_node(node, (config or {}).get("ssh")).probe()

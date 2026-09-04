# -*- coding: utf-8 -*-
"""schemas — node/job/task/capability/result/policy の schema と軽量バリデータ（仕様 §29）。

標準ライブラリのみ（jsonschema 非依存）。type/required/properties/items/enum を解釈する。
schemas/*.json は本モジュールから生成し、tests が同期を検証する。
"""

TASK_STATES = ["pending", "assigned", "running", "succeeded", "failed",
               "retrying", "cancel_requested", "cancelled", "timed_out",
               "lost", "quarantined"]
JOB_STATES = ["pending", "planned", "running", "partial", "succeeded",
              "failed", "cancelled"]
RISK_CLASSES = ["read_only", "reversible", "high_risk"]
FAILURE_CLASSES = ["transient", "resource_exhaustion", "node_offline",
                   "invalid_input", "permission_denied", "dependency_missing",
                   "policy_denied", "deterministic_failure", "unknown"]
TRUST_LEVELS = ["untrusted", "low", "medium", "high"]
EXECUTORS = ["shell", "python", "claude-code", "local-llm", "external-api",
             "ffmpeg", "ocr", "document-summary", "checksum", "custom-script"]
TRANSPORTS = ["local", "ssh"]
COMMAND_TYPES = ["inspect", "execute", "put_file", "get_file", "cancel", "ping"]

_JSON_TYPES = {"object": dict, "array": list, "string": str, "integer": int,
               "number": (int, float), "boolean": bool, "null": type(None)}


def _type_ok(value, tspec):
    for t in (tspec if isinstance(tspec, list) else [tspec]):
        py = _JSON_TYPES.get(t)
        if py is None:
            return True
        if t in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate(obj, schema, path="$", errors=None):
    if errors is None:
        errors = []
    t = schema.get("type")
    if t is not None and not _type_ok(obj, t):
        errors.append("%s: type != %s (got %s)" % (path, t, type(obj).__name__))
        return errors
    enum = schema.get("enum")
    if enum is not None and obj not in enum:
        errors.append("%s: enum 外 %r" % (path, obj))
    if isinstance(obj, dict):
        for req in schema.get("required", []):
            if req not in obj:
                errors.append("%s: required '%s' 欠落" % (path, req))
        props = schema.get("properties", {})
        for k, v in obj.items():
            if k in props:
                validate(v, props[k], "%s.%s" % (path, k), errors)
    elif isinstance(obj, list):
        it = schema.get("items")
        if it:
            for i, x in enumerate(obj):
                validate(x, it, "%s[%d]" % (path, i), errors)
    return errors


CAPABILITY_SCHEMA = {
    "type": "object",
    "required": ["node_id", "collected_at"],
    "properties": {
        "node_id": {"type": "string"},
        "collected_at": {"type": "string"},
        "os_version": {"type": ["string", "null"]},
        "architecture": {"type": ["string", "null"]},
        "cpu": {"type": ["string", "null"]},
        "cpu_cores": {"type": ["integer", "null"]},
        "memory_gb": {"type": ["number", "null"]},
        "free_disk_gb": {"type": ["number", "null"]},
        "gpu": {"type": ["string", "null"]},
        "power_source": {"type": ["string", "null"]},
        "battery_percent": {"type": ["number", "null"]},
        "thermal_state": {"type": ["string", "null"]},
        "tools": {"type": "object"},
        "models": {"type": "array", "items": {"type": "string"}},
    },
}

NODE_SCHEMA = {
    "type": "object",
    "required": ["node_id", "display_name", "host", "transport", "trust"],
    "properties": {
        "node_id": {"type": "string"},
        "display_name": {"type": "string"},
        "host": {"type": "string"},
        "user": {"type": ["string", "null"]},
        "transport": {"type": "string", "enum": TRANSPORTS},
        "trust": {"type": "string", "enum": TRUST_LEVELS},
        "labels": {"type": "array", "items": {"type": "string"}},
        "work_root": {"type": ["string", "null"]},
        "enabled": {"type": "boolean"},
        "host_key_fingerprint": {"type": ["string", "null"]},
        "capabilities": {"type": "object"},
        "current_load": {"type": "object"},
        "last_heartbeat": {"type": ["string", "null"]},
    },
}

TASK_SCHEMA = {
    "type": "object",
    "required": ["type", "executor"],
    "properties": {
        "type": {"type": "string"},
        "executor": {"type": "string", "enum": EXECUTORS},
        "input": {"type": ["array", "string", "null"], "items": {"type": "string"}},
        "argv": {"type": "array", "items": {"type": "string"}},
        "params": {"type": "object"},
        "requirements": {"type": "object"},
        "timeout_s": {"type": ["integer", "number"]},
        "max_output_bytes": {"type": "integer"},
    },
}

JOB_SCHEMA = {
    "type": "object",
    "required": ["name", "tasks"],
    "properties": {
        "name": {"type": "string"},
        "policy": {"type": ["string", "null"]},
        "priority": {"type": ["integer", "number"]},
        "tasks": {"type": "array", "items": TASK_SCHEMA},
        "aggregation": {"type": ["object", "null"]},
    },
}

RESULT_SCHEMA = {
    "type": "object",
    "required": ["task_id", "status"],
    "properties": {
        "task_id": {"type": "string"},
        "status": {"type": "string", "enum": TASK_STATES},
        "exit_code": {"type": ["integer", "null"]},
        "failure_class": {"type": ["string", "null"], "enum": FAILURE_CLASSES + [None]},
        "artifacts": {"type": "array"},
        "stdout_excerpt": {"type": ["string", "null"]},
        "stderr_excerpt": {"type": ["string", "null"]},
        "duration_s": {"type": ["number", "null"]},
        "node_id": {"type": ["string", "null"]},
    },
}

POLICY_SCHEMA = {
    "type": "object",
    "properties": {
        "external_network": {"type": "boolean"},
        "external_ai_api": {"type": "boolean"},
        "prefer_local_models": {"type": "boolean"},
        "external_api_budget_usd": {"type": "number"},
        "max_nodes": {"type": "integer"},
        "artifact_encryption": {"type": "boolean"},
        "allowed_nodes": {"type": "object"},
        "require_power": {"type": "boolean"},
        "min_battery_percent": {"type": "number"},
    },
}

ENVELOPE_SCHEMA = {
    "type": "object",
    "required": ["protocol_version", "job_id", "task_id", "node_id",
                 "command_type", "payload_hash", "created_at", "expires_at"],
    "properties": {
        "protocol_version": {"type": "string"},
        "job_id": {"type": "string"},
        "task_id": {"type": "string"},
        "attempt_id": {"type": ["string", "null"]},
        "node_id": {"type": "string"},
        "command_type": {"type": "string", "enum": COMMAND_TYPES},
        "payload_hash": {"type": "string"},
        "created_at": {"type": "string"},
        "expires_at": {"type": "string"},
        "permissions": {"type": "object"},
        "resource_limits": {"type": "object"},
        "result_destination": {"type": ["string", "null"]},
        "payload": {"type": "object"},
    },
}

SCHEMAS_BY_NAME = {
    "node": NODE_SCHEMA, "job": JOB_SCHEMA, "task": TASK_SCHEMA,
    "capability": CAPABILITY_SCHEMA, "result": RESULT_SCHEMA, "policy": POLICY_SCHEMA,
}
